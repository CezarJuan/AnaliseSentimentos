"""Carga de artefatos (léxico, emojis, config) e cálculo do score léxico."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Mapping, Sequence

from .preprocessamento import (
    CONECTIVOS_CONTRASTE,
    INTENSIFICADORES,
    PONT,
    PREFIXO_NEG,
    normalizar,
)

FATOR_NEGACAO = -0.8
PESO_APOS_CONTRASTE = 1.5
PESO_ANTES_CONTRASTE = 0.5


class ErroArtefato(Exception):
    """Artefato ausente, ilegível ou malformado."""


# --- Carga -------------------------------------------------------------------


def _linhas_tsv(conteudo: str, arquivo: str):
    for n, linha in enumerate(conteudo.splitlines(), start=1):
        linha = linha.strip()
        if not linha or linha.startswith("#"):
            continue
        partes = linha.split("\t")
        if len(partes) != 2 or not partes[0].strip():
            raise ErroArtefato(
                f"{arquivo}, linha {n}: esperado 'termo<TAB>valor', obtido {linha!r}"
            )
        yield n, partes[0].strip(), partes[1].strip()


def carregar_lexico(conteudo: str, arquivo: str = "lexico.tsv") -> dict[str, float]:
    lexico: dict[str, float] = {}
    for n, termo, valor in _linhas_tsv(conteudo, arquivo):
        try:
            polaridade = float(valor)
        except ValueError:
            raise ErroArtefato(f"{arquivo}, linha {n}: polaridade inválida {valor!r}") from None
        if not -1.0 <= polaridade <= 1.0:
            raise ErroArtefato(f"{arquivo}, linha {n}: polaridade {polaridade} fora de [-1, 1]")
        chave = normalizar(termo)
        if chave in lexico:
            raise ErroArtefato(f"{arquivo}, linha {n}: termo duplicado {termo!r} (normalizado: {chave!r})")
        lexico[chave] = polaridade
    return lexico


def carregar_emojis(conteudo: str, arquivo: str = "emojis.tsv") -> dict[str, str]:
    emojis: dict[str, str] = {}
    vistos: set[str] = set()
    for n, simbolo, polaridade in _linhas_tsv(conteudo, arquivo):
        if polaridade not in ("pos", "neg"):
            raise ErroArtefato(f"{arquivo}, linha {n}: polaridade deve ser 'pos' ou 'neg', obtido {polaridade!r}")
        chave = simbolo.lower() if simbolo.isascii() else normalizar(simbolo)
        if chave in vistos:
            raise ErroArtefato(f"{arquivo}, linha {n}: símbolo duplicado {simbolo!r}")
        vistos.add(chave)
        emojis[simbolo] = polaridade
    return emojis


@dataclass(frozen=True)
class Config:
    versao: str
    limiar_neutro: float = 0.15
    max_caracteres: int = 5000


def carregar_config(conteudo: str, arquivo: str = "config.json") -> Config:
    try:
        dados = json.loads(conteudo)
    except json.JSONDecodeError as e:
        raise ErroArtefato(f"{arquivo}: JSON inválido ({e})") from None
    if not isinstance(dados, dict) or not isinstance(dados.get("versao"), str):
        raise ErroArtefato(f"{arquivo}: campo obrigatório 'versao' (string) ausente")
    # Campos desconhecidos são ignorados (compatibilidade com artefatos futuros).
    return Config(
        versao=dados["versao"],
        limiar_neutro=float(dados.get("limiar_neutro", 0.15)),
        max_caracteres=int(dados.get("max_caracteres", 5000)),
    )


# --- Score léxico ------------------------------------------------------------


@dataclass(frozen=True)
class FeaturesLexicas:
    score: float
    n_pos: int
    n_neg: int
    contribuicoes: tuple[tuple[str, float], ...] | None


def features_lexicas(
    tokens: Sequence[str],
    lexico: Mapping[str, float],
    explicar: bool = False,
) -> FeaturesLexicas:
    """Score léxico normalizado em [-1, 1] (design.md, D3)."""
    ultimo_contraste = -1
    for i, tok in enumerate(tokens):
        if tok in CONECTIVOS_CONTRASTE:
            ultimo_contraste = i

    soma = 0.0
    peso = 1.0
    n_pos = n_neg = 0
    contribuicoes: list[tuple[str, float]] | None = [] if explicar else None

    for i, tok in enumerate(tokens):
        fator = INTENSIFICADORES.get(tok)
        if fator is not None:
            peso = fator
            continue
        if tok == PONT:
            peso = 1.0
            continue
        negado = tok.startswith(PREFIXO_NEG)
        v = lexico.get(tok[len(PREFIXO_NEG):] if negado else tok)
        if not v:
            continue  # o peso pendente segue para o próximo termo do léxico
        if negado:
            v *= FATOR_NEGACAO
        if ultimo_contraste < 0 or i == ultimo_contraste:
            c = 1.0
        elif i > ultimo_contraste:
            c = PESO_APOS_CONTRASTE
        else:
            c = PESO_ANTES_CONTRASTE
        x = v * peso * c
        soma += x
        peso = 1.0
        if x > 0:
            n_pos += 1
        elif x < 0:
            n_neg += 1
        if contribuicoes is not None:
            contribuicoes.append((tok, x))

    score = math.tanh(soma / math.sqrt(len(tokens) + 1)) if tokens else 0.0
    return FeaturesLexicas(
        score,
        n_pos,
        n_neg,
        tuple(contribuicoes) if contribuicoes is not None else None,
    )
