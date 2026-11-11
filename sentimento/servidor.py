"""Servidor HTTP local: API JSON + página da interface web (spec `api-local`).

Só biblioteca padrão. Escuta exclusivamente em 127.0.0.1 (design.md, D1/D2).
"""

from __future__ import annotations

import json
import math
import socket
import socketserver
import sys
import threading
import time
from collections import deque
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from typing import TextIO
from urllib.parse import urlsplit

from .analisador import Analisador

HOST = "127.0.0.1"
MAX_CORPO = 16 * 1024 * 1024
MAX_LOTE = 10_000
JANELA_LATENCIAS = 1_000

CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
    "connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
)

# Tabela fixa de estáticos: não existe servidor de arquivos genérico (sem path traversal).
ESTATICOS = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/logica.js": ("logica.js", "text/javascript; charset=utf-8"),
    "/estilo.css": ("estilo.css", "text/css; charset=utf-8"),
}
ROTAS_API = {"/api/analisar": "POST", "/api/lote": "POST", "/api/saude": "GET"}


def carregar_estaticos() -> dict[str, tuple[bytes, str]]:
    base = resources.files("sentimento").joinpath("web")
    cache: dict[str, bytes] = {}
    tabela = {}
    for rota, (arquivo, tipo) in ESTATICOS.items():
        if arquivo not in cache:
            cache[arquivo] = base.joinpath(arquivo).read_bytes()
        tabela[rota] = (cache[arquivo], tipo)
    return tabela


class JanelaLatencias:
    """Últimas N latências de análise (ms), segura para várias threads."""

    def __init__(self, tamanho: int = JANELA_LATENCIAS):
        self._valores: deque[float] = deque(maxlen=tamanho)
        self._lock = threading.Lock()

    def registrar(self, ms: float) -> None:
        with self._lock:
            self._valores.append(ms)

    def p95(self) -> float | None:
        with self._lock:
            valores = sorted(self._valores)
        if not valores:
            return None
        k = max(0, math.ceil(0.95 * len(valores)) - 1)
        return round(valores[k], 3)


class _ErroHTTP(Exception):
    def __init__(self, status: int, mensagem: str, fechar: bool = False):
        super().__init__(mensagem)
        self.status = status
        self.mensagem = mensagem
        self.fechar = fechar


class ServidorSentimento(ThreadingHTTPServer):
    daemon_threads = True
    # No Windows, SO_REUSEADDR permite dois processos na mesma porta; usa-se SO_EXCLUSIVEADDRUSE.
    allow_reuse_address = sys.platform != "win32"

    def __init__(self, analisador: Analisador, porta: int, log: TextIO | None):
        self.analisador = analisador
        self.latencias = JanelaLatencias()
        self.estaticos = carregar_estaticos()
        self.log = log
        self._lock_log = threading.Lock()
        super().__init__((HOST, porta), _Manipulador)

    def server_bind(self) -> None:
        if sys.platform == "win32" and hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        # TCPServer.server_bind direto: HTTPServer chamaria socket.getfqdn() (consulta DNS).
        socketserver.TCPServer.server_bind(self)
        self.server_name, self.server_port = self.server_address[:2]

    @property
    def porta(self) -> int:
        return self.server_address[1]

    @property
    def url(self) -> str:
        return f"http://{HOST}:{self.porta}/"

    def handle_error(self, request, client_address) -> None:
        # Cliente que desconecta no meio (ex.: fetch cancelado por AbortController) não é erro.
        if isinstance(sys.exc_info()[1], ConnectionError):
            return
        super().handle_error(request, client_address)

    def registrar_log(self, linha: str) -> None:
        if self.log is not None:
            with self._lock_log:
                self.log.write(linha + "\n")
                self.log.flush()


def criar_servidor(analisador: Analisador, porta: int = 8080, log: TextIO | None = sys.stderr) -> ServidorSentimento:
    """Cria (sem iniciar) o servidor em 127.0.0.1:porta. Porta 0 escolhe uma livre."""
    return ServidorSentimento(analisador, porta, log)


class _Manipulador(BaseHTTPRequestHandler):
    server: ServidorSentimento
    protocol_version = "HTTP/1.1"  # keep-alive: reduz a latência de ida e volta
    server_version = "sentimento"
    sys_version = ""

    # --- Infra ---------------------------------------------------------------

    def log_message(self, format, *args):  # noqa: A002 - assinatura da stdlib
        pass  # o log padrão incluiria a linha da requisição; ver _registrar

    def _rota(self) -> str:
        return urlsplit(self.path).path

    def _registrar(self, status: int) -> None:
        inicio = getattr(self, "_inicio", None)
        ms = (time.perf_counter() - inicio) * 1000 if inicio else 0.0
        metodo = self.command or "-"
        rota = self._rota() if getattr(self, "path", None) else "-"
        self.server.registrar_log(f"{metodo} {rota} {status} {ms:.1f}ms")

    def _cabecalhos_comuns(self, api: bool) -> None:
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", CSP)
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cache-Control", "no-store" if api else "no-cache")

    def _enviar(self, status: int, corpo: bytes, tipo: str, api: bool, fechar: bool = False) -> None:
        self.send_response_only(status)
        self.send_header("Date", self.date_time_string())
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(corpo)))
        self._cabecalhos_comuns(api)
        if fechar:
            self.send_header("Connection", "close")
            self.close_connection = True
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(corpo)
        self._registrar(status)

    def _json(self, status: int, obj: dict, fechar: bool = False) -> None:
        corpo = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self._enviar(status, corpo, "application/json; charset=utf-8", api=True, fechar=fechar)

    def send_error(self, code, message=None, explain=None):
        # Erros de protocolo da stdlib (linha de requisição inválida etc.) também saem em JSON.
        # A stdlib assume HTTP/0.9 (sem linha de status) quando a versão é inválida; nenhum
        # cliente real usa 0.9, então responde-se sempre com linha de status.
        if self.request_version == "HTTP/0.9":
            self.request_version = "HTTP/1.0"
        self._json(int(code), {"erro": message or HTTPStatus(code).phrase}, fechar=True)

    # --- Despacho ------------------------------------------------------------

    def _corpo_pendente(self) -> bool:
        """Há corpo declarado que não foi lido? Então a conexão não pode ser reaproveitada."""
        if getattr(self, "_corpo_lido", False):
            return False
        try:
            return int(self.headers.get("Content-Length", "0") or 0) > 0 or bool(self.headers.get("Transfer-Encoding"))
        except ValueError:
            return True

    def _despachar(self) -> None:
        self._inicio = time.perf_counter()
        self._corpo_lido = False
        try:
            self._validar_host()
            rota = self._rota()
            metodo_api = ROTAS_API.get(rota)
            if self.command == "GET" and rota in self.server.estaticos:
                corpo, tipo = self.server.estaticos[rota]
                self._enviar(200, corpo, tipo, api=False)
            elif self.command == "GET" and rota == "/api/saude":
                self._saude()
            elif self.command == "POST" and metodo_api == "POST":
                obj = self._ler_json()
                self._analisar(obj) if rota == "/api/analisar" else self._lote(obj)
            elif metodo_api is not None or rota in self.server.estaticos:
                raise _ErroHTTP(405, f"método {self.command} não suportado em {rota}")
            else:
                raise _ErroHTTP(404, f"rota não encontrada: {rota}")
        except _ErroHTTP as e:
            self._json(e.status, {"erro": e.mensagem}, fechar=e.fechar or self._corpo_pendente())

    do_GET = do_POST = do_PUT = do_DELETE = do_PATCH = do_OPTIONS = _despachar

    def _validar_host(self) -> None:
        porta = self.server.porta
        if self.headers.get("Host", "").lower() not in (f"127.0.0.1:{porta}", f"localhost:{porta}"):
            raise _ErroHTTP(403, "cabeçalho Host não permitido", fechar=True)

    def _ler_json(self):
        tipo = self.headers.get("Content-Type", "").split(";")[0].strip().lower()
        if tipo != "application/json":
            raise _ErroHTTP(415, "Content-Type deve ser application/json", fechar=True)
        if self.headers.get("Transfer-Encoding"):
            raise _ErroHTTP(400, "Transfer-Encoding não suportado; envie Content-Length", fechar=True)
        try:
            tamanho = int(self.headers.get("Content-Length", ""))
        except ValueError:
            raise _ErroHTTP(400, "Content-Length ausente ou inválido", fechar=True) from None
        if tamanho < 0:
            raise _ErroHTTP(400, "Content-Length inválido", fechar=True)
        if tamanho > MAX_CORPO:
            raise _ErroHTTP(413, f"corpo acima de {MAX_CORPO // (1024 * 1024)} MB", fechar=True)
        corpo = self.rfile.read(tamanho)
        self._corpo_lido = True
        try:
            return json.loads(corpo.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as e:
            raise _ErroHTTP(400, f"JSON inválido: {e}") from None

    # --- Rotas ---------------------------------------------------------------

    @staticmethod
    def _explicar(obj: dict) -> bool:
        explicar = obj.get("explicar", False)
        if not isinstance(explicar, bool):
            raise _ErroHTTP(400, "campo 'explicar' deve ser booleano")
        return explicar

    def _analisar_um(self, texto: str, explicar: bool) -> dict:
        t0 = time.perf_counter()
        resultado = self.server.analisador.analisar(texto, explicar=explicar)
        ms = (time.perf_counter() - t0) * 1000
        self.server.latencias.registrar(ms)
        resultado["latencia_ms"] = round(ms, 3)
        return resultado

    def _analisar(self, obj) -> None:
        if not isinstance(obj, dict) or not isinstance(obj.get("texto"), str):
            raise _ErroHTTP(400, "campo 'texto' (string) obrigatório")
        explicar = self._explicar(obj)
        self._json(200, self._analisar_um(obj["texto"], explicar))

    def _lote(self, obj) -> None:
        if not isinstance(obj, dict) or not isinstance(obj.get("textos"), list):
            raise _ErroHTTP(400, "campo 'textos' (lista de strings) obrigatório")
        textos = obj["textos"]
        if len(textos) > MAX_LOTE:
            raise _ErroHTTP(413, f"lote com {len(textos)} textos; o máximo é {MAX_LOTE}")
        for i, t in enumerate(textos):
            if not isinstance(t, str):
                raise _ErroHTTP(400, f"textos[{i}] deve ser string")
        explicar = self._explicar(obj)
        self._json(200, {"resultados": [self._analisar_um(t, explicar) for t in textos]})

    def _saude(self) -> None:
        a = self.server.analisador
        self._json(200, {"versao": a.versao, "modo": a.modo, "latencia_p95_ms": self.server.latencias.p95()})
