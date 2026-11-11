"""Spec `api-local`: servidor, rotas, erros, segurança, concorrência e latência."""

import http.client
import json
import math
import socket
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from conftest import Cliente
from sentimento.servidor import CSP, MAX_CORPO, JanelaLatencias, criar_servidor


# --- 1.1: criação e bind ------------------------------------------------------------


def test_escuta_so_em_loopback(servidor):
    assert servidor.server_address[0] == "127.0.0.1"
    assert servidor.url == f"http://127.0.0.1:{servidor.porta}/"


def test_criar_servidor_sem_opcao_de_host():
    import inspect

    assert "host" not in inspect.signature(criar_servidor).parameters


def test_nao_responde_em_outra_interface(servidor):
    # Descobre um IP local que não seja loopback; se não houver, não há o que testar.
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))  # UDP: não envia pacote, só escolhe a interface
            ip = s.getsockname()[0]
    except OSError:
        pytest.skip("sem interface de rede além do loopback")
    if ip.startswith("127."):
        pytest.skip("sem interface de rede além do loopback")
    with pytest.raises(OSError):
        socket.create_connection((ip, servidor.porta), timeout=1).close()


def test_encerra_limpo(analisador):
    import io

    srv = criar_servidor(analisador, porta=0, log=io.StringIO())
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    assert Cliente(srv.porta).get("/api/saude").status == 200
    srv.shutdown()
    srv.server_close()
    t.join(timeout=5)
    assert not t.is_alive()


# --- 1.2: analisar e lote --------------------------------------------------------------


def test_analisar_com_explicacao(cliente):
    r = cliente.post("/api/analisar", {"texto": "nao gostei do atendimento", "explicar": True})
    assert r.status == 200
    corpo = r.json
    assert corpo["label"] == "negativo"
    assert "NEG_gostei" in [t["token"] for t in corpo["tokens"]]
    assert isinstance(corpo["latencia_ms"], (int, float))


def test_analisar_sem_explicacao(cliente, analisador):
    r = cliente.post("/api/analisar", {"texto": "adorei"})
    assert r.status == 200
    corpo = r.json
    assert "tokens" not in corpo
    corpo.pop("latencia_ms")
    assert corpo == analisador.analisar("adorei")


def test_analisar_utf8(cliente):
    r = cliente.post("/api/analisar", {"texto": "ótimo 😍"})
    assert r.status == 200 and r.json["label"] == "positivo"
    assert r.headers["content-type"] == "application/json; charset=utf-8"


def test_lote_equivale_a_individuais(cliente, analisador):
    textos = ["adorei", "pessimo", ""]
    r = cliente.post("/api/lote", {"textos": textos})
    assert r.status == 200
    resultados = r.json["resultados"]
    assert len(resultados) == 3
    for res, t in zip(resultados, textos):
        res.pop("latencia_ms")
        assert res == analisador.analisar(t)


def test_lote_com_explicacao(cliente):
    r = cliente.post("/api/lote", {"textos": ["nao gostei"], "explicar": True})
    assert "tokens" in r.json["resultados"][0]


def test_lote_vazio(cliente):
    assert cliente.post("/api/lote", {"textos": []}).json == {"resultados": []}


def test_lote_no_limite(cliente):
    r = cliente.post("/api/lote", {"textos": ["ok"] * 10_000})
    assert r.status == 200 and len(r.json["resultados"]) == 10_000


def test_lote_acima_do_limite(cliente, servidor):
    r = cliente.post("/api/lote", {"textos": ["ok"] * 10_001})
    assert r.status == 413
    assert "erro" in r.json
    assert servidor.latencias.p95() is None  # nada foi analisado


def test_lote_item_invalido_nao_analisa_nada(cliente, servidor):
    r = cliente.post("/api/lote", {"textos": ["ok", 3, "x"]})
    assert r.status == 400
    assert "textos[1]" in r.json["erro"]
    assert servidor.latencias.p95() is None


# --- 1.3: saúde ----------------------------------------------------------------------


def test_saude_antes_de_analises(cliente):
    r = cliente.get("/api/saude")
    assert r.status == 200
    assert r.json == {"versao": "0.1.0", "modo": "lexico", "latencia_p95_ms": None}


def test_saude_depois_de_analises(cliente):
    for i in range(10):
        cliente.post("/api/analisar", {"texto": f"texto {i} muito bom"})
    p95 = cliente.get("/api/saude").json["latencia_p95_ms"]
    assert isinstance(p95, float) and p95 > 0


def test_janela_de_latencias():
    j = JanelaLatencias(tamanho=1000)
    assert j.p95() is None
    for v in range(1, 1201):  # só as últimas 1000 (201..1200) contam
        j.registrar(float(v))
    assert j.p95() == float(200 + math.ceil(0.95 * 1000))


def test_janela_thread_safe():
    j = JanelaLatencias(tamanho=100_000)
    with ThreadPoolExecutor(8) as ex:
        list(ex.map(lambda _: [j.registrar(1.0) for _ in range(1000)], range(8)))
    assert len(j._valores) == 8000


# --- 1.4: erros e Host -----------------------------------------------------------------


def test_json_invalido(cliente):
    r = cliente.post("/api/analisar", "nao e json", headers={"Content-Type": "application/json"})
    assert r.status == 400 and "erro" in r.json


@pytest.mark.parametrize("corpo", [{"texto": 42}, {"outro": "x"}, ["lista"], {"texto": "ok", "explicar": "sim"}])
def test_campo_com_tipo_errado(cliente, corpo):
    r = cliente.post("/api/analisar", corpo)
    assert r.status == 400 and "erro" in r.json


def test_lote_sem_lista(cliente):
    assert cliente.post("/api/lote", {"textos": "adorei"}).status == 400


@pytest.mark.parametrize("tipo", ["text/plain", "application/x-www-form-urlencoded", "multipart/form-data", None])
def test_content_type_nao_json(cliente, servidor, tipo):
    headers = {"Content-Type": tipo} if tipo else {}
    r = cliente.post("/api/analisar", '{"texto": "adorei"}', headers=headers)
    assert r.status == 415 and "erro" in r.json
    assert servidor.latencias.p95() is None


def test_content_type_json_com_charset(cliente):
    r = cliente.post("/api/analisar", '{"texto": "adorei"}', headers={"Content-Type": "application/json; charset=utf-8"})
    assert r.status == 200


def test_rota_desconhecida(cliente):
    r = cliente.get("/api/nada")
    assert r.status == 404 and "erro" in r.json


@pytest.mark.parametrize("metodo,rota", [("GET", "/api/analisar"), ("GET", "/api/lote"), ("POST", "/api/saude"),
                                         ("PUT", "/api/analisar"), ("DELETE", "/"), ("POST", "/")])
def test_metodo_nao_suportado(cliente, metodo, rota):
    r = cliente.requisitar(metodo, rota, {"texto": "x"} if metodo in ("POST", "PUT") else None)
    assert r.status == 405 and "erro" in r.json


def test_erro_com_corpo_nao_lido_fecha_conexao(servidor):
    # Regressão: o corpo não lido de um 405 era interpretado como a próxima requisição.
    conn = http.client.HTTPConnection("127.0.0.1", servidor.porta, timeout=10)
    conn.request("POST", "/api/saude", body=b'{"texto": "x"}',
                 headers={"Host": f"127.0.0.1:{servidor.porta}", "Content-Type": "application/json"})
    r = conn.getresponse()
    r.read()
    assert r.status == 405
    assert r.getheader("Connection") == "close"
    conn.close()


def test_keep_alive_em_sucesso(servidor):
    conn = http.client.HTTPConnection("127.0.0.1", servidor.porta, timeout=10)
    h = {"Host": f"127.0.0.1:{servidor.porta}", "Content-Type": "application/json"}
    for texto in ["adorei", "pessimo", "ok"]:
        conn.request("POST", "/api/analisar", body=json.dumps({"texto": texto}), headers=h)
        r = conn.getresponse()
        r.read()
        assert r.status == 200 and r.getheader("Connection") != "close"
    conn.close()


def test_corpo_acima_de_16mb(servidor):
    # Declara um corpo enorme sem enviá-lo: o servidor recusa antes de ler.
    conn = http.client.HTTPConnection("127.0.0.1", servidor.porta, timeout=10)
    conn.putrequest("POST", "/api/analisar", skip_host=True)
    conn.putheader("Host", f"127.0.0.1:{servidor.porta}")
    conn.putheader("Content-Type", "application/json")
    conn.putheader("Content-Length", str(MAX_CORPO + 1))
    conn.endheaders()
    r = conn.getresponse()
    assert r.status == 413
    assert "erro" in json.loads(r.read())
    conn.close()


@pytest.mark.parametrize("host", ["site-malicioso.com:{p}", "127.0.0.1:1", "localhost", "", "127.0.0.1.nip.io:{p}"])
def test_host_invalido(cliente, servidor, host):
    r = cliente.post("/api/analisar", {"texto": "adorei"}, host=host.format(p=servidor.porta))
    assert r.status == 403 and "erro" in r.json
    assert servidor.latencias.p95() is None


@pytest.mark.parametrize("host", ["127.0.0.1:{p}", "localhost:{p}", "LOCALHOST:{p}"])
def test_host_valido(cliente, servidor, host):
    assert cliente.get("/api/saude", host=host.format(p=servidor.porta)).status == 200


@pytest.mark.parametrize("bruto", [b"LIXO / HTTP/1.1\r\nHost: 127.0.0.1:{p}\r\n\r\n",
                                   b"GET / HTTP/9.9\r\nHost: 127.0.0.1:{p}\r\n\r\n"])
def test_requisicao_malformada_responde_json(servidor, bruto):
    with socket.create_connection(("127.0.0.1", servidor.porta), timeout=5) as s:
        s.sendall(bruto.replace(b"{p}", str(servidor.porta).encode()))
        dados = b""
        while bloco := s.recv(65536):  # o servidor fecha a conexão após o erro
            dados += bloco
    assert dados.startswith(b"HTTP/1.")
    assert b'"erro"' in dados


# --- 1.5: cabeçalhos e log -----------------------------------------------------------------


def test_cabecalhos_na_api(cliente):
    h = cliente.get("/api/saude").headers
    assert h["x-content-type-options"] == "nosniff"
    assert "default-src 'self'" in h["content-security-policy"]
    assert h["cache-control"] == "no-store"
    assert not any(k.startswith("access-control-") for k in h)


def test_cabecalhos_na_pagina(cliente):
    h = cliente.get("/").headers
    assert h["content-security-policy"] == CSP
    assert h["x-content-type-options"] == "nosniff"


def test_cabecalhos_em_erro(cliente):
    h = cliente.get("/api/nada").headers
    assert h["x-content-type-options"] == "nosniff"
    assert h["cache-control"] == "no-store"


def test_options_sem_cors(cliente):
    r = cliente.requisitar("OPTIONS", "/api/analisar", headers={
        "Origin": "https://outro.site", "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "content-type"})
    assert "access-control-allow-origin" not in r.headers
    assert r.status == 405


def test_log_sem_texto(cliente, servidor):
    cliente.post("/api/analisar", {"texto": "segredo123"})
    cliente.post("/api/lote", {"textos": ["segredo456"]})
    cliente.get("/api/saude?q=segredo789")
    log = servidor.log_capturado.getvalue()
    assert "segredo" not in log
    linhas = log.strip().splitlines()
    assert linhas[0].startswith("POST /api/analisar 200 ") and linhas[0].endswith("ms")
    assert linhas[2].startswith("GET /api/saude 200 ")


def test_log_de_erro(cliente, servidor):
    cliente.get("/api/nada")
    assert servidor.log_capturado.getvalue().startswith("GET /api/nada 404 ")


# --- 1.6: concorrência e ida e volta -----------------------------------------------------------


def test_concorrencia(cliente):
    textos = [f"cliente {i} " + ("adorei demais" if i % 2 else "pessimo atendimento") for i in range(8)]

    def enviar(texto):
        r = cliente.post("/api/analisar", {"texto": texto, "explicar": True})
        return texto, r.json

    barreira = threading.Barrier(8)

    def sincronizado(texto):
        barreira.wait()
        return enviar(texto)

    with ThreadPoolExecutor(8) as ex:
        respostas = list(ex.map(sincronizado, textos * 5))
    for texto, corpo in respostas:
        esperado = "positivo" if "adorei" in texto else "negativo"
        assert corpo["label"] == esperado


def test_ida_e_volta_p95_ate_50ms(servidor):
    # Conexão persistente, como o navegador faz (keep-alive).
    conn = http.client.HTTPConnection("127.0.0.1", servidor.porta, timeout=10)
    headers = {"Host": f"127.0.0.1:{servidor.porta}", "Content-Type": "application/json"}
    tempos = []
    for i in range(500):
        corpo = json.dumps({"texto": f"o produto chegou rapido, adorei! pedido {i}", "explicar": True})
        t0 = time.perf_counter()
        conn.request("POST", "/api/analisar", body=corpo, headers=headers)
        r = conn.getresponse()
        r.read()
        tempos.append((time.perf_counter() - t0) * 1000)
        assert r.status == 200
    conn.close()
    tempos.sort()
    p95 = tempos[math.ceil(0.95 * len(tempos)) - 1]
    assert p95 <= 50, f"p95 de ida e volta = {p95:.1f} ms"
