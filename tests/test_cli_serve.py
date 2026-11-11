"""Spec `api-local`: subcomando `sentimento serve` (via subprocesso, como o usuário usaria)."""

import json
import os
import signal
import socket
import subprocess
import sys
import urllib.request

import pytest


def porta_livre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def iniciar(*args):
    flags = subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0
    return subprocess.Popen(
        [sys.executable, "-m", "sentimento", "serve", *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env={**os.environ, "PYTHONUNBUFFERED": "1"},
        creationflags=flags,
    )


def interromper(proc):
    # Windows: Ctrl+C não pode ser enviado a outro grupo de processos; Ctrl+Break é o equivalente.
    proc.send_signal(signal.CTRL_BREAK_EVENT if sys.platform == "win32" else signal.SIGINT)
    return proc.wait(timeout=10)


def test_serve_imprime_url_responde_e_encerra_com_0():
    porta = porta_livre()
    proc = iniciar("--porta", str(porta))
    try:
        linha = proc.stdout.readline().decode("utf-8")
        assert f"http://127.0.0.1:{porta}/" in linha
        with urllib.request.urlopen(f"http://127.0.0.1:{porta}/api/saude", timeout=5) as r:
            assert json.loads(r.read())["modo"] == "lexico"
        with urllib.request.urlopen(f"http://127.0.0.1:{porta}/", timeout=5) as r:
            assert r.status == 200
    finally:
        codigo = interromper(proc)
    assert codigo == 0
    log = proc.stderr.read().decode("utf-8")
    assert "GET /api/saude 200" in log


def test_serve_porta_padrao_8080():
    # Só verifica o padrão se a 8080 estiver livre nesta máquina.
    with socket.socket() as s:
        try:
            s.bind(("127.0.0.1", 8080))
        except OSError:
            pytest.skip("porta 8080 ocupada nesta máquina")
    proc = iniciar()
    try:
        assert "http://127.0.0.1:8080/" in proc.stdout.readline().decode("utf-8")
    finally:
        interromper(proc)


def test_serve_porta_ocupada():
    with socket.socket() as ocupante:
        ocupante.bind(("127.0.0.1", 0))
        ocupante.listen()
        porta = ocupante.getsockname()[1]
        r = subprocess.run([sys.executable, "-m", "sentimento", "serve", "--porta", str(porta)],
                           capture_output=True, timeout=20)
    assert r.returncode == 2
    assert str(porta) in r.stderr.decode("utf-8")
    assert r.stdout == b""


def test_serve_modelo_inexistente():
    r = subprocess.run([sys.executable, "-m", "sentimento", "serve", "--modelo", "pasta_inexistente",
                        "--porta", str(porta_livre())], capture_output=True, timeout=20)
    assert r.returncode == 2
    assert "pasta_inexistente" in r.stderr.decode("utf-8")


def test_serve_porta_invalida():
    r = subprocess.run([sys.executable, "-m", "sentimento", "serve", "--porta", "99999"], capture_output=True, timeout=20)
    assert r.returncode == 2


def test_texto_literal_serve():
    r = subprocess.run([sys.executable, "-m", "sentimento", "--", "serve"], capture_output=True, timeout=20)
    assert r.returncode == 0
    resultado = json.loads(r.stdout)
    assert resultado["label"] == "neutro" and resultado["modo"] == "lexico"


def test_ajuda_menciona_serve():
    r = subprocess.run([sys.executable, "-m", "sentimento", "--help"], capture_output=True, timeout=20)
    assert b"sentimento -- serve" in r.stdout
