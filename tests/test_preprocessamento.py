"""Spec `preprocessamento-texto`."""

import subprocess
import sys
from pathlib import Path

import pytest

DADOS = Path(__file__).parent / "dados" / "preprocessamento.tsv"


# --- 2.1: normalização, placeholders, emojis/emoticons ------------------------


def test_texto_com_e_sem_acento_igual(tok):
    assert tok("Péssimo, NÃO gostei") == tok("pessimo, nao gostei")


def test_url_mencao_numero(tok):
    assert tok("@loja comprei 2 em https://ex.com/p") == ("<user>", "comprei", "<num>", "em", "<url>")


def test_www_e_numero_decimal(tok):
    assert tok("veja www.loja.com.br paguei 19,90") == ("veja", "<url>", "paguei", "<num>")


def test_emoji_positivo(tok):
    assert tok("amei 😍") == ("amei", "<emo_pos>")


def test_emoji_com_e_sem_variation_selector(tok):
    assert tok("❤️") == tok("❤") == ("<emo_pos>",)


def test_emoji_com_tom_de_pele(tok):
    assert tok("👍🏽 valeu") == ("<emo_pos>", "valeu")


def test_emoji_colado_em_palavra(tok):
    assert tok("odiei😡") == ("odiei", "<emo_neg>")


@pytest.mark.parametrize("texto", ["chegou rapido :D", "chegou rapido :d"])
def test_emoticon_D_qualquer_caixa(tok, texto):
    assert tok(texto)[-1] == "<emo_pos>"


@pytest.mark.parametrize("texto", ["XD adorei", "xd adorei", "Xd adorei"])
def test_emoticon_XD(tok, texto):
    assert tok(texto) == ("<emo_pos>", "adorei")


def test_emoticon_negativo_antes_de_pontuacao(tok):
    assert tok("atrasou :(.") == ("atrasou", "<emo_neg>", "<pont>")


def test_emoticon_coracao(tok):
    assert tok("te amo <3") == ("te", "amo", "<emo_pos>")


def test_emoticon_dentro_de_url_nao_casa(tok):
    # ":/" existe dentro de "https://"; a URL deve virar <url> inteira, sem <emo_neg>.
    assert tok("olha https://site.com/a:/b") == ("olha", "<url>")
    assert "<emo_neg>" not in tok("http://x.com e :/ ruim")[:1]
    assert tok("http://x.com e :/ ruim") == ("<url>", "e", "<emo_neg>", "ruim")


def test_emoticon_exige_borda(tok):
    # Sem espaço antes, ":)" não é reconhecido (design D2); os símbolos são descartados.
    assert tok("obrigado:)") == ("obrigado", "<pont>")


# --- 2.2: risadas e alongamentos ----------------------------------------------


@pytest.mark.parametrize("risada", ["kkkkkkk", "KKK", "rsrsrs", "rsrs", "hahaha", "HAHAHA", "ahahah", "hehehe", "huahuahua"])
def test_risadas(analisador, risada):
    p = analisador.preprocessar(f"{risada} muito bom")
    assert p.tokens[0] == "<riso>"
    assert p.tokens[1:] == ("muito", "bom")


def test_risada_longa_nao_marca_alongamento(analisador):
    p = analisador.preprocessar("kkkkkkk")
    assert p.tokens == ("<riso>",)
    assert p.alongado is False


@pytest.mark.parametrize("palavra", ["kk", "rs", "haha"])
def test_risadas_curtas_ou_ambiguas(tok, palavra):
    # "kk" e "rs" têm menos de 3 caracteres; "haha" tem 4 e é risada.
    esperado = ("<riso>",) if palavra == "haha" else (palavra,)
    assert tok(palavra) == esperado


def test_alongamento(analisador):
    p = analisador.preprocessar("muuuuito bom")
    assert p.tokens == ("muito", "bom")
    assert p.alongado is True


def test_letra_dupla_legitima(analisador):
    p = analisador.preprocessar("carro")
    assert p.tokens == ("carro",)
    assert p.alongado is False


def test_alongamento_com_acento(analisador):
    p = analisador.preprocessar("lindoooo demaaais")
    assert p.tokens == ("lindo", "demais")
    assert p.alongado


# --- 2.3: tokenização e abreviações --------------------------------------------


def test_exclamacoes(tok):
    assert tok("adorei!!!") == ("adorei", "<excl>")


def test_interrogacoes(tok):
    assert tok("serio???") == ("serio", "<interr>")


def test_virgula_vira_fronteira(tok):
    assert tok("ruim, caro") == ("ruim", "<pont>", "caro")


def test_reticencias_viram_uma_fronteira(tok):
    assert tok("sei la... talvez") == ("sei", "la", "<pont>", "talvez")


def test_simbolos_descartados(tok):
    assert tok("(bom) - \"ok\" #top *") == ("bom", "ok", "top")


def test_abreviacoes(tok):
    assert tok("vc n vai gostar mt") == ("voce", "nao", "NEG_vai", "NEG_gostar", "muito")


def test_abreviacao_so_por_token_inteiro(tok):
    # o "n" dentro de palavras não vira "nao"
    assert tok("nunca") == ("nunca",)
    assert tok("ganhei tb") == ("ganhei", "tambem")
    assert tok("nd") == ("nada",)
    assert tok("mto bom") == ("muito", "bom")
    assert tok("vcs") == ("voces",)


# --- 2.4: escopo de negação ------------------------------------------------------


def test_negacao_simples(tok):
    assert tok("nao gostei") == ("nao", "NEG_gostei")


def test_negacao_termina_na_pontuacao(tok):
    toks = tok("nao gostei, mas o preco e bom")
    assert [t for t in toks if t.startswith("NEG_")] == ["NEG_gostei"]
    assert "mas" in toks


def test_intensificador_dentro_do_escopo(tok):
    assert tok("nao e muito bom") == ("nao", "NEG_e", "muito", "NEG_bom")


def test_limite_de_3_tokens(tok):
    assert tok("nao achei o produto bom") == ("nao", "NEG_achei", "NEG_o", "NEG_produto", "bom")


def test_negacao_para_em_outro_negador(tok):
    assert tok("nao gostei nada") == ("nao", "NEG_gostei", "nada")


def test_negacao_para_em_conectivo(tok):
    assert tok("nao mas bom") == ("nao", "mas", "bom")


@pytest.mark.parametrize("fronteira", ["!", "?", ";", ":"])
def test_negacao_para_em_qualquer_fronteira(tok, fronteira):
    toks = tok(f"nao{fronteira} bom")
    assert toks[-1] == "bom"


def test_placeholder_imune_e_conta_no_limite(tok):
    assert tok("nao 😍 gostei muito disso") == ("nao", "<emo_pos>", "NEG_gostei", "muito", "disso")


@pytest.mark.parametrize("negador", ["nao", "nunca", "nem", "jamais", "nada", "ninguem", "ninguém", "não"])
def test_todos_os_negadores(tok, negador):
    assert tok(f"{negador} gostei")[-1] == "NEG_gostei"


# --- Entrada vazia ----------------------------------------------------------------


@pytest.mark.parametrize("texto", ["", "   ", "\n\t", "(-)", "#*&"])
def test_entrada_sem_tokens(tok, texto):
    assert tok(texto) == ()


# --- 2.5: tabela de regressão e determinismo --------------------------------------


def _casos_regressao():
    casos = []
    for n, linha in enumerate(DADOS.read_text(encoding="utf-8").splitlines(), start=1):
        if not linha.strip() or linha.startswith("#"):
            continue
        texto, esperado = linha.split("\t")
        casos.append(pytest.param(texto, tuple(esperado.split()), id=f"L{n}"))
    return casos


def test_tabela_tem_pelo_menos_40_casos():
    assert len(_casos_regressao()) >= 40


@pytest.mark.parametrize("texto,esperado", _casos_regressao())
def test_tabela_de_regressao(tok, texto, esperado):
    assert tok(texto) == esperado


def test_determinismo_entre_processos(tok):
    textos = [linha.split("\t")[0] for linha in DADOS.read_text(encoding="utf-8").splitlines()
              if linha.strip() and not linha.startswith("#")]
    codigo = (
        "import sys, json\n"
        "from sentimento import Analisador\n"
        "a = Analisador.carregar()\n"
        "textos = json.loads(sys.stdin.read())\n"
        "print(json.dumps([list(a.preprocessar(t).tokens) for t in textos]))\n"
    )
    import json

    saidas = []
    for _ in range(2):
        r = subprocess.run(
            [sys.executable, "-c", codigo],
            input=json.dumps(textos).encode("utf-8"),
            capture_output=True,
            check=True,
        )
        saidas.append(json.loads(r.stdout))
    assert saidas[0] == saidas[1] == [list(tok(t)) for t in textos]
