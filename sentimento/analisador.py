"""API pública: `Analisador.carregar()`, `analisar()` e `analisar_lote()`."""

from __future__ import annotations

import warnings
from importlib import resources
from pathlib import Path
from typing import Iterable

from .lexico import (
    Config,
    ErroArtefato,
    carregar_config,
    carregar_emojis,
    carregar_lexico,
    features_lexicas,
)
from .preprocessamento import Preprocessado, Preprocessador

ARQUIVOS_OBRIGATORIOS = ("lexico.tsv", "emojis.tsv", "config.json")
CASAS_DECIMAIS = 4  # arredondamento garante saída idêntica entre plataformas
MAX_TOKENS_EXPLICACAO = 5

__all__ = ["Analisador", "ErroArtefato"]


class Analisador:
    """Classificador de sentimento. Nesta versão opera só no modo léxico."""

    modo = "lexico"

    def __init__(self, lexico: dict[str, float], emojis: dict[str, str], config: Config):
        self._lexico = lexico
        self._config = config
        self._preprocessador = Preprocessador(emojis)

    # --- Carga ---------------------------------------------------------------

    @classmethod
    def carregar(cls, diretorio: str | Path | None = None) -> "Analisador":
        """Carrega os artefatos de `diretorio` ou, se omitido, os embutidos no pacote."""
        if diretorio is None:
            base = resources.files("sentimento").joinpath("recursos")
            conteudos = {nome: base.joinpath(nome).read_text(encoding="utf-8") for nome in ARQUIVOS_OBRIGATORIOS}
        else:
            pasta = Path(diretorio)
            if not pasta.is_dir():
                raise ErroArtefato(f"diretório de artefatos não encontrado: {pasta}")
            conteudos = {}
            for nome in ARQUIVOS_OBRIGATORIOS:
                arquivo = pasta / nome
                if not arquivo.is_file():
                    raise ErroArtefato(f"artefato obrigatório ausente: {nome} (em {pasta})")
                try:
                    conteudos[nome] = arquivo.read_text(encoding="utf-8")
                except (OSError, UnicodeDecodeError) as e:
                    raise ErroArtefato(f"não foi possível ler {nome}: {e}") from None
            if (pasta / "W.npy").exists():
                warnings.warn(
                    "W.npy encontrado, mas esta versão só suporta o modo léxico; o modelo será ignorado",
                    stacklevel=2,
                )
        return cls(
            carregar_lexico(conteudos["lexico.tsv"]),
            carregar_emojis(conteudos["emojis.tsv"]),
            carregar_config(conteudos["config.json"]),
        )

    # --- Propriedades ----------------------------------------------------------

    @property
    def versao(self) -> str:
        return self._config.versao

    @property
    def preprocessador(self) -> Preprocessador:
        return self._preprocessador

    def preprocessar(self, texto: str) -> Preprocessado:
        return self._preprocessador.preprocessar(texto)

    # --- Análise ---------------------------------------------------------------

    def analisar(self, texto: str, explicar: bool = False) -> dict:
        """Classifica um texto. Ver spec `classificacao-sentimento`."""
        if not isinstance(texto, str):
            raise TypeError(f"texto deve ser str, não {type(texto).__name__}")

        cfg = self._config
        truncado = len(texto) > cfg.max_caracteres
        if truncado:
            texto = texto[: cfg.max_caracteres]

        tokens = self._preprocessador.preprocessar(texto).tokens
        feats = features_lexicas(tokens, self._lexico, explicar=explicar)
        score = round(feats.score, CASAS_DECIMAIS) + 0.0  # + 0.0 normaliza -0.0

        if not tokens:
            label, confianca = "neutro", 0.0
        elif score > cfg.limiar_neutro:
            label, confianca = "positivo", abs(score)
        elif score < -cfg.limiar_neutro:
            label, confianca = "negativo", abs(score)
        else:
            label, confianca = "neutro", 1.0 - abs(score) / cfg.limiar_neutro

        resultado = {
            "label": label,
            "score": score,
            "confianca": round(min(max(confianca, 0.0), 1.0), CASAS_DECIMAIS),
            "versao": cfg.versao,
            "modo": self.modo,
            "truncado": truncado,
        }
        if explicar:
            resultado["tokens"] = _top_tokens(feats.contribuicoes or ())
        return resultado

    def analisar_lote(self, textos: Iterable[str], explicar: bool = False) -> list[dict]:
        """Classifica uma lista de textos, preservando ordem e tamanho."""
        if isinstance(textos, str):
            raise TypeError("analisar_lote espera uma lista de textos, não uma str")
        return [self.analisar(t, explicar=explicar) for t in textos]


def _top_tokens(contribuicoes) -> list[dict]:
    # Ordenação estável: empates mantêm a ordem de aparição (determinismo).
    ordenadas = sorted(contribuicoes, key=lambda tc: -abs(tc[1]))
    return [
        {"token": tok, "peso": round(peso, CASAS_DECIMAIS) + 0.0}
        for tok, peso in ordenadas[:MAX_TOKENS_EXPLICACAO]
    ]
