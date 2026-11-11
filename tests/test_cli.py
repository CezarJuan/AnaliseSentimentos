"""Spec `cli-sentimento` (executada via subprocesso, como o usuário usaria)."""

import json
import os
import subprocess
import sys

import pytest


def rodar(*args: str, entrada: str | None = None, ambiente: dict | None = None):
    env = {**os.environ, **(ambiente or {})}
    r = subprocess.run(
        [sys.executable, "-m", "sentimento", *args],
        input=entrada.encode("utf-8") if entrada is not None else b"",
        capture_output=True,
        env=env,
    )
    return r.returncode, r.stdout.decode("utf-8"), r.stderr.decode("utf-8")


def linhas_json(saida: str) -> list[dict]:
    return [json.loads(l) for l in saida.splitlines()]


# --- 5.1: texto avulso e opções -------------------------------------------------


def test_texto_como_argumento():
    codigo, saida, _ = rodar("adorei o produto")
    assert codigo == 0
    [r] = linhas_json(saida)
    assert r["label"] == "positivo"


def test_texto_com_acento_e_emoji_como_argumento():
    codigo, saida, _ = rodar("ótimo 😍")
    assert codigo == 0
    assert linhas_json(saida)[0]["label"] == "positivo"


def test_explicar():
    codigo, saida, _ = rodar("--explicar", "nao gostei")
    assert codigo == 0
    [r] = linhas_json(saida)
    assert r["tokens"][0]["token"] == "NEG_gostei"


def test_versao():
    codigo, saida, _ = rodar("--versao")
    assert (codigo, saida.strip()) == (0, "0.1.0")


def test_modelo_inexistente():
    codigo, saida, erro = rodar("--modelo", "pasta_inexistente", "oi")
    assert codigo == 2
    assert saida == ""
    assert "pasta_inexistente" in erro


def test_modelo_sem_lexico(tmp_path):
    (tmp_path / "config.json").write_text('{"versao": "x"}', encoding="utf-8")
    codigo, _, erro = rodar("--modelo", str(tmp_path), "oi")
    assert codigo == 2
    assert "lexico.tsv" in erro


def test_opcao_invalida():
    codigo, _, _ = rodar("--nao-existe")
    assert codigo == 2


# --- 5.2: JSONL pela stdin ----------------------------------------------------------


def test_jsonl_com_id():
    entrada = '{"id": 1, "texto": "adorei"}\n{"id": 2, "texto": "pessimo"}\n'
    codigo, saida, _ = rodar(entrada=entrada)
    assert codigo == 0
    r1, r2 = linhas_json(saida)
    assert (r1["id"], r1["label"]) == (1, "positivo")
    assert (r2["id"], r2["label"]) == (2, "negativo")
    assert list(r1)[0] == "id"


def test_jsonl_sem_id():
    codigo, saida, _ = rodar(entrada='{"texto": "adorei"}\n')
    assert codigo == 0
    [r] = linhas_json(saida)
    assert "id" not in r


def test_jsonl_ignora_linhas_em_branco():
    codigo, saida, _ = rodar(entrada='\n{"texto": "a"}\n   \n\n{"texto": "b"}\n')
    assert codigo == 0
    assert len(linhas_json(saida)) == 2


def test_jsonl_linha_malformada():
    entrada = '{"texto": "adorei"}\nnao e json\n{"texto": "pessimo"}\n'
    codigo, saida, _ = rodar(entrada=entrada)
    assert codigo == 1
    r1, r2, r3 = linhas_json(saida)
    assert r1["label"] == "positivo"
    assert r2["linha"] == 2 and "erro" in r2
    assert r3["label"] == "negativo"


@pytest.mark.parametrize("linha", ['{"id": 7}', '{"texto": 3}', '["lista"]', '"so texto"'])
def test_jsonl_sem_texto_string(linha):
    codigo, saida, _ = rodar(entrada=linha + "\n")
    assert codigo == 1
    [r] = linhas_json(saida)
    assert r["linha"] == 1 and "erro" in r
    if linha.startswith('{"id"'):
        assert r["id"] == 7


def test_jsonl_explicar():
    _, saida, _ = rodar("--explicar", entrada='{"texto": "nao gostei"}\n')
    assert "tokens" in linhas_json(saida)[0]


def test_jsonl_vazio():
    codigo, saida, _ = rodar(entrada="")
    assert (codigo, saida) == (0, "")


def test_utf8_na_stdin_mesmo_com_codificacao_legada():
    # Simula um console Windows com cp1252: a CLI deve forçar UTF-8 mesmo assim.
    entrada = '{"texto": "ótimo 😍", "id": "ç"}\n'
    codigo, saida, _ = rodar("--explicar", entrada=entrada, ambiente={"PYTHONIOENCODING": "cp1252", "PYTHONUTF8": "0"})
    assert codigo == 0
    [r] = linhas_json(saida)
    assert r["label"] == "positivo"
    assert r["id"] == "ç"
    assert "ç" in saida  # sem escapes \uXXXX


def test_bom_na_entrada_e_descartado():
    codigo, saida, _ = rodar(entrada='﻿{"texto": "adorei"}\n')
    assert codigo == 0
    assert linhas_json(saida)[0]["label"] == "positivo"
