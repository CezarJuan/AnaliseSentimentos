"""Spec `interface-web`: estrutura da página, offline, tamanho, contraste e entrega dos estáticos."""

import re
from html.parser import HTMLParser
from pathlib import Path

import pytest

WEB = Path(__file__).parent.parent / "sentimento" / "web"
ESTATICOS = ["index.html", "estilo.css", "app.js", "logica.js"]


class Coletor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags = []  # (tag, attrs)
        self.scripts_inline = 0
        self._em_script = False
        self._script_tem_src = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        self.tags.append((tag, a))
        if tag == "script":
            self._em_script, self._script_tem_src = True, "src" in a

    def handle_endtag(self, tag):
        if tag == "script":
            self._em_script = False

    def handle_data(self, data):
        if self._em_script and not self._script_tem_src and data.strip():
            self.scripts_inline += 1


@pytest.fixture(scope="module")
def pagina():
    c = Coletor()
    c.feed((WEB / "index.html").read_text(encoding="utf-8"))
    return c


# --- 4.1: estrutura, offline e sem inline ------------------------------------------------


def test_sem_urls_externas():
    for nome in ESTATICOS:
        conteudo = (WEB / nome).read_text(encoding="utf-8")
        assert not re.search(r"https?://|//[a-z0-9.-]+\.[a-z]{2,}/|@import", conteudo, re.I), nome


def test_sem_script_ou_estilo_inline(pagina):
    assert pagina.scripts_inline == 0
    assert all("style" not in attrs for _, attrs in pagina.tags)
    assert all(not any(k.startswith("on") for k in attrs) for _, attrs in pagina.tags)
    assert "style" not in [t for t, _ in pagina.tags]


def test_recursos_locais(pagina):
    srcs = [a.get("src") or a.get("href") for t, a in pagina.tags if t in ("script", "link")]
    assert set(srcs) == {"/app.js", "/estilo.css", "data:,"}


def test_estrutura_acessivel(pagina):
    ids = {a.get("id"): (t, a) for t, a in pagina.tags if a.get("id")}
    assert ("html", "pt-BR") in [(t, a.get("lang")) for t, a in pagina.tags]
    for obrigatorio in ["texto", "analisar", "arquivo", "baixar", "limpar", "tema", "status", "historico", "tokens"]:
        assert obrigatorio in ids, obrigatorio
    assert ids["anuncio"][1].get("aria-live") == "polite"
    barra = ids["barra"][1]
    assert barra["role"] == "meter" and barra["aria-valuemin"] == "-1" and barra["aria-valuemax"] == "1"
    assert any(t == "label" and a.get("for") == "texto" for t, a in pagina.tags)
    assert {"main", "header", "footer"} <= {t for t, _ in pagina.tags}


def test_ordem_de_foco(pagina):
    focaveis = [a["id"] for t, a in pagina.tags
                if t in ("textarea", "button", "input") and a.get("id")]
    assert focaveis == ["texto", "analisar", "arquivo", "baixar", "limpar", "tema"]


def test_app_nao_usa_innerhtml():
    js = (WEB / "app.js").read_text(encoding="utf-8")
    assert not re.search(r"\.(innerHTML|outerHTML)\s*[+]?=|insertAdjacentHTML|document\.write", js)


def test_app_so_guarda_tema_no_navegador():
    js = (WEB / "app.js").read_text(encoding="utf-8") + (WEB / "logica.js").read_text(encoding="utf-8")
    assert "sessionStorage" not in js and "indexedDB" not in js and "document.cookie" not in js
    assert re.findall(r"localStorage\.setItem\((\w+)", js) == ["CHAVE_TEMA"]


# --- Contraste AA nos dois temas --------------------------------------------------------------


def _luminancia(hexa: str) -> float:
    r, g, b = (int(hexa[i:i + 2], 16) / 255 for i in (1, 3, 5))
    lin = lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4  # noqa: E731
    return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)


def _contraste(a: str, b: str) -> float:
    la, lb = sorted((_luminancia(a), _luminancia(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def _temas():
    css = (WEB / "estilo.css").read_text(encoding="utf-8")
    blocos = {
        "claro": re.search(r":root \{(.*?)\}", css, re.S).group(1),
        "escuro": re.search(r':root\[data-theme="dark"\] \{(.*?)\}', css, re.S).group(1),
        "escuro-sistema": re.search(r':root:not\(\[data-theme="light"\]\) \{(.*?)\}', css, re.S).group(1),
    }
    return {nome: dict(re.findall(r"--([\w-]+):\s*(#[0-9a-fA-F]{6})", corpo)) for nome, corpo in blocos.items()}


def test_tema_escuro_do_sistema_igual_ao_manual():
    temas = _temas()
    assert temas["escuro"] == temas["escuro-sistema"]


PARES_TEXTO = [  # (cor do texto, cor do fundo)
    ("texto", "fundo"), ("texto", "superficie"), ("suave", "fundo"), ("suave", "superficie"),
    ("destaque-texto", "destaque"), ("pos", "superficie"), ("neg", "superficie"), ("neu", "superficie"),
    ("pos", "pos-fundo"), ("neg", "neg-fundo"), ("neu", "neu-fundo"), ("texto", "neu-fundo"),
    ("texto", "pos-fundo"), ("texto", "neg-fundo"), ("suave", "neu-fundo"),
]


@pytest.mark.parametrize("tema", ["claro", "escuro"])
@pytest.mark.parametrize("texto,fundo", PARES_TEXTO)
def test_contraste_aa(tema, texto, fundo):
    cores = _temas()[tema]
    razao = _contraste(cores[texto], cores[fundo])
    assert razao >= 4.5, f"{tema}: --{texto} sobre --{fundo} = {razao:.2f}:1"


@pytest.mark.parametrize("tema", ["claro", "escuro"])
def test_foco_visivel_contraste(tema):
    cores = _temas()[tema]  # contorno de foco precisa de 3:1 contra o fundo (WCAG 1.4.11)
    assert _contraste(cores["foco"], cores["superficie"]) >= 3
    assert _contraste(cores["foco"], cores["fundo"]) >= 3


# --- 4.4: entrega pelo servidor e tamanho -------------------------------------------------------


def test_estaticos_ate_100kb():
    total = sum((WEB / n).stat().st_size for n in ESTATICOS)
    assert total <= 100 * 1024, f"{total} bytes"


@pytest.mark.parametrize("rota,tipo,arquivo", [
    ("/", "text/html; charset=utf-8", "index.html"),
    ("/index.html", "text/html; charset=utf-8", "index.html"),
    ("/app.js", "text/javascript; charset=utf-8", "app.js"),
    ("/logica.js", "text/javascript; charset=utf-8", "logica.js"),
    ("/estilo.css", "text/css; charset=utf-8", "estilo.css"),
])
def test_estaticos_servidos(cliente, rota, tipo, arquivo):
    r = cliente.get(rota)
    assert r.status == 200
    assert r.headers["content-type"] == tipo
    assert r.corpo == (WEB / arquivo).read_bytes()


@pytest.mark.parametrize("rota", ["/../pyproject.toml", "/recursos/lexico.tsv", "/web/app.js", "/favicon.ico", "/%2e%2e/x"])
def test_sem_acesso_a_outros_arquivos(cliente, rota):
    assert cliente.get(rota).status == 404
