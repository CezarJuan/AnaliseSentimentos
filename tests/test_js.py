"""Testes do JavaScript da interface, via Node (pulados se o Node não estiver instalado)."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from sentimento.preprocessamento import ABREVIACOES, _RE_ALONGAMENTO, normalizar

RAIZ = Path(__file__).parent.parent
LOGICA = RAIZ / "sentimento" / "web" / "logica.js"
NODE = shutil.which("node")

pytestmark = pytest.mark.skipif(NODE is None, reason="Node.js não instalado")


def node_eval(codigo: str, entrada: str = "") -> str:
    r = subprocess.run([NODE, "--input-type=module", "-e", codigo], input=entrada.encode("utf-8"),
                       capture_output=True, timeout=60)
    assert r.returncode == 0, r.stderr.decode("utf-8")
    return r.stdout.decode("utf-8")


def test_suite_node():
    arquivos = sorted(str(p) for p in (RAIZ / "tests" / "js").glob("*.test.mjs"))
    assert arquivos
    r = subprocess.run([NODE, "--test", *arquivos], capture_output=True, timeout=120)
    saida = r.stdout.decode("utf-8") + r.stderr.decode("utf-8")
    assert r.returncode == 0, saida
    assert "ExperimentalWarning" not in saida and "MODULE_TYPELESS" not in saida, saida


PALAVRAS = [
    # acentos e caixa
    "Péssimo", "ÓTIMO", "atenção", "Coração", "AÇÚCAR", "não", "Ninguém", "você", "ÉÉÉ", "à",
    # alongamentos
    "muuuuito", "lindoooo", "demaaais", "booom", "aaaah", "carro", "assim", "Ótimooo", "zzz",
    # abreviações (e o que não é abreviação)
    "vc", "VCS", "n", "mt", "mto", "mta", "tb", "tbm", "nd", "pq", "td", "msm", "blz", "obg", "vlw",
    "nunca", "mtt", "constructor", "toString",
    # compatibilidade NFKC e formas decompostas
    "ﬁm", "Ótimo", "ｇｏｓｔｅｉ",
]


def python_normalizar_palavra(palavra: str) -> str:
    reduzida = _RE_ALONGAMENTO.sub(r"\1", normalizar(palavra))
    return ABREVIACOES.get(reduzida, reduzida)


def test_abreviacoes_identicas():
    codigo = f"import {{ ABREVIACOES }} from {json.dumps(LOGICA.as_uri())}; console.log(JSON.stringify(ABREVIACOES));"
    assert json.loads(node_eval(codigo)) == dict(ABREVIACOES)


def test_paridade_normalizacao(analisador):
    assert len(PALAVRAS) >= 30
    codigo = (
        f"import {{ normalizarPalavra }} from {json.dumps(LOGICA.as_uri())};"
        "let e=''; process.stdin.on('data', d => e += d); process.stdin.on('end', () =>"
        " console.log(JSON.stringify(JSON.parse(e).map(normalizarPalavra))));"
    )
    js = json.loads(node_eval(codigo, json.dumps(PALAVRAS)))
    py = [python_normalizar_palavra(p) for p in PALAVRAS]
    divergencias = [(p, a, b) for p, a, b in zip(PALAVRAS, js, py) if a != b]
    assert not divergencias, f"(palavra, js, python): {divergencias}"
    # Sanidade: para palavras soltas, a forma normalizada é o token que o servidor gera
    # (exceto negadores, que o servidor mantém, e prefixos NEG_ que só surgem após negador).
    for palavra, forma in zip(PALAVRAS, py):
        tokens = analisador.preprocessar(palavra).tokens
        assert tokens[0] == forma, (palavra, tokens)
