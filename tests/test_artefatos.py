"""Artefatos padrão e carga (spec `classificacao-sentimento`: Carregamento de artefatos)."""

import json
import shutil
import warnings
from pathlib import Path

import pytest

from sentimento import Analisador, ErroArtefato
from sentimento.lexico import carregar_config, carregar_emojis, carregar_lexico
from sentimento.preprocessamento import ABREVIACOES, CONECTIVOS_CONTRASTE, INTENSIFICADORES, NEGADORES

RECURSOS = Path(__file__).parent.parent / "sentimento" / "recursos"


# --- 3.1: emojis.tsv e config.json --------------------------------------------


def test_emojis_utf8_e_suficientes():
    emojis = carregar_emojis((RECURSOS / "emojis.tsv").read_bytes().decode("utf-8"))
    assert len(emojis) >= 40
    assert set(emojis.values()) == {"pos", "neg"}


def test_config_padrao():
    cfg = carregar_config((RECURSOS / "config.json").read_text(encoding="utf-8"))
    assert cfg.versao == "0.1.0"
    assert cfg.limiar_neutro == 0.15
    assert cfg.max_caracteres == 5000


# --- 3.2: léxico semente ----------------------------------------------------------


@pytest.fixture(scope="module")
def lexico():
    return carregar_lexico((RECURSOS / "lexico.tsv").read_bytes().decode("utf-8"))


def test_lexico_tamanho_e_faixa(lexico):
    assert 300 <= len(lexico) <= 600
    assert all(-1.0 <= v <= 1.0 and v != 0 for v in lexico.values())


def test_lexico_tem_placeholders(lexico):
    assert lexico["<emo_pos>"] > 0
    assert lexico["<emo_neg>"] < 0
    assert lexico["<riso>"] > 0


def test_lexico_nao_contem_regras(lexico):
    regras = NEGADORES | CONECTIVOS_CONTRASTE | set(INTENSIFICADORES) | set(ABREVIACOES)
    assert not regras & set(lexico), "negadores/intensificadores/conectivos/abreviações são regras, não termos"


def test_lexico_termos_sao_um_token(lexico, tok):
    for termo in lexico:
        assert tok(termo) == (termo,), f"termo {termo!r} não sobrevive ao pré-processamento intacto"


def test_recursos_ate_20_mb():
    total = sum(p.stat().st_size for p in RECURSOS.iterdir() if p.is_file())
    assert total <= 20 * 1024 * 1024


# --- 3.3: carga ----------------------------------------------------------------


def test_lexico_normaliza_acentos():
    assert carregar_lexico("Péssimo\t-0.9\n") == {"pessimo": -0.9}


def test_lexico_duplicata_apos_normalizacao():
    with pytest.raises(ErroArtefato, match="duplicado"):
        carregar_lexico("ótimo\t0.8\notimo\t0.8\n")


@pytest.mark.parametrize("linha", ["bom\n", "bom\tmuito\n", "bom\t2.0\n", "\t0.5\n"])
def test_lexico_linha_malformada(linha):
    with pytest.raises(ErroArtefato, match="linha 1"):
        carregar_lexico(linha)


def test_emojis_polaridade_invalida():
    with pytest.raises(ErroArtefato, match="pos"):
        carregar_emojis(":)\tfeliz\n")


def test_emoticon_duplicado_por_caixa():
    with pytest.raises(ErroArtefato, match="duplicado"):
        carregar_emojis(":D\tpos\n:d\tpos\n")


def test_config_ignora_campos_desconhecidos():
    cfg = carregar_config(json.dumps({"versao": "9", "dim_hash": 262144, "seed": 1}))
    assert cfg.versao == "9"


def test_config_sem_versao():
    with pytest.raises(ErroArtefato, match="versao"):
        carregar_config("{}")


@pytest.fixture
def dir_artefatos(tmp_path):
    destino = tmp_path / "modelo"
    shutil.copytree(RECURSOS, destino)
    return destino


def test_carregar_diretorio_valido(dir_artefatos):
    (dir_artefatos / "config.json").write_text('{"versao": "2.0.0-teste"}', encoding="utf-8")
    a = Analisador.carregar(dir_artefatos)
    assert a.analisar("adorei")["versao"] == "2.0.0-teste"


def test_carregar_padrao_usa_versao_embutida():
    assert Analisador.carregar().analisar("oi")["versao"] == "0.1.0"


@pytest.mark.parametrize("arquivo", ["lexico.tsv", "emojis.tsv", "config.json"])
def test_diretorio_sem_artefato_nomeia_arquivo(dir_artefatos, arquivo):
    (dir_artefatos / arquivo).unlink()
    with pytest.raises(ErroArtefato, match=arquivo.replace(".", r"\.")):
        Analisador.carregar(dir_artefatos)


def test_diretorio_inexistente(tmp_path):
    with pytest.raises(ErroArtefato, match="não encontrado"):
        Analisador.carregar(tmp_path / "nao_existe")


def test_lexico_com_duplicata_no_diretorio(dir_artefatos):
    with open(dir_artefatos / "lexico.tsv", "a", encoding="utf-8") as f:
        f.write("ótimo\t0.1\n")
    with pytest.raises(ErroArtefato, match="duplicado"):
        Analisador.carregar(dir_artefatos)


def test_aviso_quando_ha_modelo(dir_artefatos):
    (dir_artefatos / "W.npy").write_bytes(b"")
    with warnings.catch_warnings(record=True) as avisos:
        warnings.simplefilter("always")
        a = Analisador.carregar(dir_artefatos)
    assert any("W.npy" in str(w.message) for w in avisos)
    assert a.analisar("adorei")["modo"] == "lexico"
