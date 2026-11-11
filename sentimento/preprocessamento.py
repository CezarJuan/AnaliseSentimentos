"""Pré-processamento de texto em PT-BR informal.

Este módulo é o contrato compartilhado entre a inferência e o treino: qualquer
mudança na saída de `Preprocessador.preprocessar` invalida modelos já treinados
e exige mudança de versão em `config.json`.

Ordem das etapas (design.md, D2):
  [a] URLs e menções             [f] alongamentos 3+ -> 1
  [b] emoticons ASCII            [g] tokenização com fronteiras
  [c] NFKC + minúsculas + acentos [h] abreviações por token inteiro
  [d] emojis Unicode e números   [i] escopo de negação (NEG_)
  [e] risadas
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Mapping

# --- Tabelas gramaticais (versionadas com o código, ver design D4) ----------

NEGADORES = frozenset({"nao", "nunca", "nem", "jamais", "nada", "ninguem"})

INTENSIFICADORES: Mapping[str, float] = {
    "muito": 1.5,
    "super": 1.5,
    "demais": 1.5,
    "extremamente": 1.5,
    "pouco": 0.5,
    "meio": 0.5,
    "quase": 0.5,
}

CONECTIVOS_CONTRASTE = frozenset({"mas", "porem", "entretanto", "contudo"})

ABREVIACOES: Mapping[str, str] = {
    "vc": "voce",
    "vcs": "voces",
    "n": "nao",
    "mt": "muito",
    "mto": "muito",
    "mta": "muita",
    "tb": "tambem",
    "tbm": "tambem",
    "nd": "nada",
    "pq": "porque",
    "td": "tudo",
    "msm": "mesmo",
    "blz": "beleza",
    "obg": "obrigado",
    "vlw": "valeu",
}

PONT = "<pont>"
EXCL = "<excl>"
INTERR = "<interr>"
FRONTEIRAS = frozenset({PONT, EXCL, INTERR})

PREFIXO_NEG = "NEG_"
ESCOPO_NEGACAO = 3

# --- Regex compiladas na importação ------------------------------------------

_RE_URL = re.compile(r"(?i)\b(?:https?://|www\.)\S+")
_RE_MENCAO = re.compile(r"(?<!\w)@\w+")
_RE_NUMERO = re.compile(r"\d+(?:[.,]\d+)*")
_RE_RISADA = re.compile(
    r"\b(?:k{3,}|(?:rs){2,}r?|a?(?:ha){2,}h?a*|e?(?:he){2,}h?e*|(?:hu[ae]){2,})\b"
)
_RE_ALONGAMENTO = re.compile(r"([^\W\d_])\1{2,}")
_RE_TOKEN = re.compile(r"<\w+>|\w+|[.,;:]+|!+|\?+")


def normalizar(texto: str) -> str:
    """Etapa [c]: NFKC, minúsculas e remoção de marcas combinantes (acentos, VS16)."""
    if texto.isascii():
        return texto.lower()
    texto = unicodedata.normalize("NFKC", texto).lower()
    decomposto = unicodedata.normalize("NFD", texto)
    return "".join(c for c in decomposto if unicodedata.category(c) != "Mn")


def eh_placeholder(token: str) -> bool:
    return token.startswith("<") and token.endswith(">")


@dataclass(frozen=True)
class Preprocessado:
    tokens: tuple[str, ...]
    alongado: bool


def _alternancia(chaves) -> str:
    # Mais longas primeiro, para ":-)" vencer ":-" e assim por diante.
    return "|".join(re.escape(c) for c in sorted(chaves, key=lambda c: (-len(c), c)))


class Preprocessador:
    """Pré-processador configurado com uma tabela de emojis/emoticons.

    `emojis` mapeia símbolo -> "pos" | "neg". Entradas só com ASCII são
    tratadas como emoticons (casadas sem diferenciar caixa, contra o texto
    original e com borda); as demais são emojis Unicode (casadas após a
    normalização).
    """

    def __init__(self, emojis: Mapping[str, str]):
        self._emoticons: dict[str, str] = {}
        self._emojis: dict[str, str] = {}
        for simbolo, polaridade in emojis.items():
            placeholder = "<emo_pos>" if polaridade == "pos" else "<emo_neg>"
            if simbolo.isascii():
                self._emoticons[simbolo.lower()] = placeholder
            else:
                self._emojis[normalizar(simbolo)] = placeholder

        self._re_emoticon = (
            re.compile(
                r"(?i)(?<!\S)(?:" + _alternancia(self._emoticons) + r")(?=$|\s|[.,;:!?])"
            )
            if self._emoticons
            else None
        )
        self._re_emoji = (
            re.compile(_alternancia(self._emojis)) if self._emojis else None
        )

    def _sub_emoticon(self, m: re.Match) -> str:
        return " " + self._emoticons[m.group(0).lower()] + " "

    def _sub_emoji(self, m: re.Match) -> str:
        return " " + self._emojis[m.group(0)] + " "

    def preprocessar(self, texto: str) -> Preprocessado:
        # [a] URLs e menções (antes dos emoticons: ":/" casaria em "https://")
        t = _RE_URL.sub(" <url> ", texto)
        t = _RE_MENCAO.sub(" <user> ", t)
        # [b] emoticons ASCII, antes das minúsculas (":D", "XD")
        if self._re_emoticon is not None:
            t = self._re_emoticon.sub(self._sub_emoticon, t)
        # [c] normalização
        t = normalizar(t)
        # [d] emojis Unicode e números
        if self._re_emoji is not None and not t.isascii():
            t = self._re_emoji.sub(self._sub_emoji, t)
        t = _RE_NUMERO.sub(" <num> ", t)
        # [e] risadas (antes do alongamento, senão "kkkk" -> "k")
        t = _RE_RISADA.sub(" <riso> ", t)
        # [f] alongamentos
        t, n_along = _RE_ALONGAMENTO.subn(r"\1", t)
        # [g] tokenização + [h] abreviações
        brutos = []
        for tok in _RE_TOKEN.findall(t):
            c = tok[0]
            if c == "!":
                brutos.append(EXCL)
            elif c == "?":
                brutos.append(INTERR)
            elif c in ".,;:":
                brutos.append(PONT)
            else:
                brutos.append(ABREVIACOES.get(tok, tok))
        # [i] escopo de negação
        return Preprocessado(tuple(_aplicar_negacao(brutos)), n_along > 0)


def _aplicar_negacao(tokens: list[str]) -> list[str]:
    saida = []
    restante = 0
    for tok in tokens:
        if tok in FRONTEIRAS or tok in CONECTIVOS_CONTRASTE:
            restante = 0
            saida.append(tok)
        elif tok in NEGADORES:
            restante = ESCOPO_NEGACAO
            saida.append(tok)
        elif restante > 0:
            restante -= 1
            if eh_placeholder(tok) or tok in INTENSIFICADORES:
                saida.append(tok)
            else:
                saida.append(PREFIXO_NEG + tok)
        else:
            saida.append(tok)
    return saida
