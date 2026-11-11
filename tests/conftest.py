import http.client
import io
import json
import threading
from dataclasses import dataclass

import pytest

from sentimento import Analisador


@pytest.fixture(scope="session")
def analisador() -> Analisador:
    return Analisador.carregar()


@pytest.fixture(scope="session")
def tok(analisador):
    """Atalho: texto -> tupla de tokens."""
    return lambda texto: analisador.preprocessar(texto).tokens


@dataclass
class Resposta:
    status: int
    headers: dict
    corpo: bytes

    @property
    def json(self):
        return json.loads(self.corpo.decode("utf-8"))


class Cliente:
    """Cliente HTTP mínimo para os testes do servidor (uma conexão nova por chamada)."""

    def __init__(self, porta: int):
        self.porta = porta

    def requisitar(self, metodo, rota, corpo=None, headers=None, host=None) -> Resposta:
        conn = http.client.HTTPConnection("127.0.0.1", self.porta, timeout=10)
        h = {"Host": host if host is not None else f"127.0.0.1:{self.porta}", **(headers or {})}
        if isinstance(corpo, (dict, list)):
            corpo = json.dumps(corpo).encode("utf-8")
            h.setdefault("Content-Type", "application/json")
        elif isinstance(corpo, str):
            corpo = corpo.encode("utf-8")
        conn.request(metodo, rota, body=corpo, headers=h)
        r = conn.getresponse()
        resposta = Resposta(r.status, {k.lower(): v for k, v in r.getheaders()}, r.read())
        conn.close()
        return resposta

    def get(self, rota, **kw):
        return self.requisitar("GET", rota, **kw)

    def post(self, rota, corpo, **kw):
        return self.requisitar("POST", rota, corpo, **kw)


@pytest.fixture
def servidor(analisador):
    """Servidor real numa porta livre, rodando em thread; log capturado em memória."""
    from sentimento.servidor import criar_servidor

    log = io.StringIO()
    srv = criar_servidor(analisador, porta=0, log=log)
    thread = threading.Thread(target=srv.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
    thread.start()
    srv.log_capturado = log
    yield srv
    srv.shutdown()
    srv.server_close()
    thread.join(timeout=5)


@pytest.fixture
def cliente(servidor) -> Cliente:
    return Cliente(servidor.porta)
