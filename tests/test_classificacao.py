"""Spec `classificacao-sentimento`."""

import json
import socket
import subprocess
import sys

import pytest

from sentimento import Analisador
from sentimento.lexico import Config, features_lexicas

CAMPOS = ["label", "score", "confianca", "versao", "modo", "truncado"]


# --- 4.1: score léxico -----------------------------------------------------------


def test_negacao_inverte(analisador):
    assert analisador.analisar("gostei")["score"] > 0
    assert analisador.analisar("nao gostei")["score"] < 0


def test_negacao_atenua_com_fator_08():
    lex = {"bom": 0.5}
    pos = features_lexicas(["bom", "x"], lex).score
    neg = features_lexicas(["NEG_bom", "x"], lex).score
    assert neg == pytest.approx(-features_lexicas(["bom", "x"], {"bom": 0.4}).score)
    assert abs(neg) < abs(pos)


def test_intensificador_amplia(analisador):
    assert analisador.analisar("muito bom")["score"] > analisador.analisar("bom")["score"]


def test_atenuador_reduz():
    lex = {"bom": 0.6}
    assert features_lexicas(["pouco", "bom"], lex).score < features_lexicas(["o", "bom"], lex).score


def test_intensificador_consumido_pelo_proximo_termo_do_lexico():
    lex = {"bom": 0.6}
    # "muito" pula "o" (fora do léxico) e amplia "bom"
    assert features_lexicas(["muito", "o", "bom"], lex).score == pytest.approx(
        features_lexicas(["x", "o", "bom"], {"bom": 0.9}).score
    )


def test_pont_zera_intensificador():
    lex = {"bom": 0.6}
    assert features_lexicas(["muito", "<pont>", "bom"], lex).score == pytest.approx(
        features_lexicas(["x", "<pont>", "bom"], lex).score
    )


def test_contraste_privilegia_segunda_oracao(analisador):
    assert analisador.analisar("o produto e bom, mas a entrega foi pessima")["label"] == "negativo"
    assert analisador.analisar("a entrega foi pessima, mas o produto e otimo")["label"] == "positivo"


def test_contraste_vale_o_ultimo_conectivo():
    lex = {"bom": 0.6, "ruim": -0.6}
    f = features_lexicas(["bom", "mas", "ruim", "porem", "bom"], lex, explicar=True)
    assert dict(f.contribuicoes[:1]) == {"bom": pytest.approx(0.3)}  # antes do último: 0,5
    assert f.contribuicoes[1] == ("ruim", pytest.approx(-0.3))
    assert f.contribuicoes[2] == ("bom", pytest.approx(0.9))  # depois do último: 1,5


def test_riso_e_emojis_contam(analisador):
    assert analisador.analisar("chegou hoje kkkk 😍")["score"] > 0
    assert analisador.analisar("chegou hoje 😡")["score"] < 0


def test_contagens_pos_neg():
    f = features_lexicas(["bom", "ruim", "NEG_ruim"], {"bom": 0.5, "ruim": -0.5})
    assert (f.n_pos, f.n_neg) == (2, 1)


def test_score_limitado():
    f = features_lexicas(["bom"] * 1000, {"bom": 1.0})
    assert -1.0 <= f.score <= 1.0


# --- 4.2: estrutura, limiar, confiança, truncamento, tipo -------------------------


def test_estrutura_do_resultado(analisador):
    r = analisador.analisar("o produto chegou rapido, adorei!")
    assert list(r) == CAMPOS
    assert r["label"] == "positivo"
    assert r["score"] > 0
    assert 0 <= r["confianca"] <= 1
    assert r["modo"] == "lexico"
    assert r["truncado"] is False
    assert r["versao"] == "0.1.0"


def test_texto_neutro(analisador):
    r = analisador.analisar("o pedido chegou na terca")
    assert r["label"] == "neutro"
    assert -0.15 <= r["score"] <= 0.15


def test_neutro_sem_polaridade_confianca_1(analisador):
    r = analisador.analisar("o pedido chegou na terca")
    assert r["score"] == 0.0
    assert r["confianca"] == 1.0


@pytest.mark.parametrize("texto", ["", "   ", "#*&"])
def test_texto_vazio(analisador, texto):
    r = analisador.analisar(texto)
    assert (r["label"], r["score"], r["confianca"]) == ("neutro", 0.0, 0.0)


@pytest.mark.parametrize(
    "texto",
    ["adorei", "pessimo", "nao gostei", "bom", "o pedido chegou", "nao e muito bom", "meio caro mas ok",
     "o produto e bom, mas a entrega foi pessima", "ok", "kkkk", "😡😡", "nem bom nem ruim"],
)
def test_label_coerente_com_score(analisador, texto):
    r = analisador.analisar(texto)
    if r["label"] == "positivo":
        assert r["score"] > 0.15 and r["confianca"] == r["score"]
    elif r["label"] == "negativo":
        assert r["score"] < -0.15 and r["confianca"] == -r["score"]
    else:
        assert -0.15 <= r["score"] <= 0.15
        assert 0 <= r["confianca"] <= 1


def test_confianca_neutro_linear():
    a = Analisador({"bom": 0.1}, {}, Config(versao="t"))
    r = a.analisar("bom o pedido")  # tanh(0.1 / 2) ~ 0.05: neutro com score não nulo
    assert r["label"] == "neutro" and r["score"] > 0
    assert r["confianca"] == pytest.approx(1 - r["score"] / 0.15, abs=1e-4)


def test_texto_longo_truncado(analisador):
    base = "adorei o produto, mas a entrega atrasou muito. " * 200
    texto = (base * 2)[:6000]
    r = analisador.analisar(texto)
    r5000 = analisador.analisar(texto[:5000])
    assert r["truncado"] is True
    assert r5000["truncado"] is False
    assert {**r, "truncado": False} == r5000


def test_texto_de_5000_nao_trunca(analisador):
    assert analisador.analisar("a" * 5000)["truncado"] is False


@pytest.mark.parametrize("valor", [42, None, b"bytes", ["lista"]])
def test_entrada_nao_string(analisador, valor):
    with pytest.raises(TypeError):
        analisador.analisar(valor)


def test_sem_zero_negativo(analisador):
    r = analisador.analisar("o pedido chegou")
    assert json.dumps(r["score"]) == "0.0"


# --- 4.3: explicação ---------------------------------------------------------------


def test_explicacao_texto_negado(analisador):
    r = analisador.analisar("nao gostei do atendimento", explicar=True)
    pesos = {t["token"]: t["peso"] for t in r["tokens"]}
    assert pesos["NEG_gostei"] < 0


def test_explicacao_ausente_por_padrao(analisador):
    assert "tokens" not in analisador.analisar("nao gostei")


def test_explicacao_top5_ordenada(analisador):
    r = analisador.analisar("otimo bom ruim pessimo lindo feio caro adorei odiei", explicar=True)
    pesos = [abs(t["peso"]) for t in r["tokens"]]
    assert len(pesos) == 5
    assert pesos == sorted(pesos, reverse=True)


def test_explicacao_sem_termos(analisador):
    assert analisador.analisar("o pedido chegou", explicar=True)["tokens"] == []


def test_explicacao_nao_muda_resultado(analisador):
    texto = "o produto e bom, mas a entrega foi pessima"
    com = analisador.analisar(texto, explicar=True)
    com.pop("tokens")
    assert com == analisador.analisar(texto)


# --- 4.4: lote ----------------------------------------------------------------------


def test_lote_equivale_a_individuais(analisador):
    textos = ["adorei", "pessimo", ""]
    assert analisador.analisar_lote(textos) == [analisador.analisar(t) for t in textos]


def test_lote_vazio(analisador):
    assert analisador.analisar_lote([]) == []


def test_lote_preserva_ordem(analisador):
    textos = ["pessimo", "adorei"] * 50
    labels = [r["label"] for r in analisador.analisar_lote(textos)]
    assert labels == ["negativo", "positivo"] * 50


def test_lote_com_explicacao(analisador):
    assert all("tokens" in r for r in analisador.analisar_lote(["a", "b"], explicar=True))


def test_lote_rejeita_str(analisador):
    with pytest.raises(TypeError):
        analisador.analisar_lote("adorei")


def test_lote_rejeita_item_nao_string(analisador):
    with pytest.raises(TypeError):
        analisador.analisar_lote(["ok", 3])


# --- 4.5: determinismo e offline ------------------------------------------------------

TEXTOS_DETERMINISMO = [
    f"{a} {b}" for a in ["adorei", "nao gostei", "muito bom", "pessimo!!!", "kkkk 😍", "meio caro"]
    for b in ["o produto", "mas a entrega atrasou", ":(", "vc n vai curtir", "nota 10", "🤬 nunca mais",
              "lindoooo", "@loja https://x.com", "ok", "", "porem chegou quebrado", "XD", "rsrs top",
              "nem bom nem ruim", "super caro", "❤️ 👍🏽"]
] + ["", "texto neutro qualquer", "x" * 6000, "Péssimo, NÃO gostei"]


def test_cem_textos_de_determinismo():
    assert len(TEXTOS_DETERMINISMO) >= 100


def test_determinismo_entre_processos(analisador):
    codigo = (
        "import sys, json\n"
        "from sentimento import Analisador\n"
        "a = Analisador.carregar()\n"
        "print(json.dumps(a.analisar_lote(json.loads(sys.stdin.read()), explicar=True), ensure_ascii=False))\n"
    )
    entrada = json.dumps(TEXTOS_DETERMINISMO).encode("utf-8")
    saidas = [
        json.loads(subprocess.run([sys.executable, "-c", codigo], input=entrada, capture_output=True, check=True).stdout)
        for _ in range(2)
    ]
    local = json.loads(json.dumps(analisador.analisar_lote(TEXTOS_DETERMINISMO, explicar=True)))
    assert saidas[0] == saidas[1] == local


def test_offline(monkeypatch):
    def proibido(*args, **kwargs):
        raise AssertionError("chamada de rede durante carga/análise")

    monkeypatch.setattr(socket, "socket", proibido)
    monkeypatch.setattr(socket, "create_connection", proibido)
    monkeypatch.setattr(socket, "getaddrinfo", proibido)
    a = Analisador.carregar()
    assert a.analisar("adorei, recomendo!")["label"] == "positivo"
    assert len(a.analisar_lote(["ok"] * 10)) == 10
