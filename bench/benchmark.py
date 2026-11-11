"""Benchmark de latência e memória do Analisador (design.md, D7).

Uso:
    python bench/benchmark.py                    # corpus sintético, 10.000 textos
    python bench/benchmark.py --arquivo textos.txt  # um texto por linha
    python bench/benchmark.py --json             # relatório em JSON

Mede cada chamada de `analisar()` com perf_counter_ns, após um aquecimento,
numa única thread.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
from pathlib import Path

SEED = 20261110
MAX_CARACTERES = 280
AQUECIMENTO = 500

_INICIOS = ["", "o produto", "a entrega", "o atendimento", "a loja", "vc", "eu", "comprei e", "@loja", "gente,"]
_MEIOS = [
    "chegou rapido", "nao gostei", "adorei", "muito bom", "pessimo", "veio quebrado", "super recomendo",
    "atrasou de novo", "funciona bem", "n vai durar mt", "achei meio caro", "nunca mais compro",
    "nao e muito bom", "lindoooo demaaais", "chegou certinho", "uma porcaria", "vale a pena", "nota 10",
]
_CONECTIVOS = ["", ", mas", " porem", ".", "!", "!!!", ", e", " e"]
_EXTRAS = ["", "", "kkkkk", "rsrs", "😍", "😡", "👍🏽", ":)", ":(", "XD", "https://loja.com/p/123", "❤️", "?"]


def corpus_sintetico(n: int = 10_000, seed: int = SEED) -> list[str]:
    rng = random.Random(seed)
    textos = []
    for _ in range(n):
        partes = []
        for _ in range(rng.randint(1, 8)):
            partes += [rng.choice(_INICIOS), rng.choice(_MEIOS), rng.choice(_CONECTIVOS), rng.choice(_EXTRAS)]
        texto = " ".join(p for p in partes if p)
        if rng.random() < 0.3:
            texto = texto.upper() if rng.random() < 0.5 else texto.capitalize()
        textos.append(texto[:MAX_CARACTERES])
    return textos


def pico_rss_bytes() -> int | None:
    """Pico de memória residente do processo, ou None se indisponível."""
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        class PMC(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        try:
            pmc = PMC()
            pmc.cb = ctypes.sizeof(PMC)
            psapi = ctypes.WinDLL("psapi")
            kernel32 = ctypes.WinDLL("kernel32")
            kernel32.GetCurrentProcess.restype = wintypes.HANDLE
            psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(PMC), wintypes.DWORD]
            if psapi.GetProcessMemoryInfo(kernel32.GetCurrentProcess(), ctypes.byref(pmc), pmc.cb):
                return int(pmc.PeakWorkingSetSize)
        except (OSError, AttributeError):
            return None
        return None
    try:
        import resource
    except ImportError:
        return None
    pico = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return pico if sys.platform == "darwin" else pico * 1024  # macOS: bytes; Linux: KiB


def _percentil(ordenados: list[int], p: float) -> int:
    # nearest-rank
    k = max(0, min(len(ordenados) - 1, int(round(p / 100 * len(ordenados) + 0.5)) - 1))
    return ordenados[k]


def executar(textos: list[str], modelo: str | None = None) -> dict:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from sentimento import Analisador

    a = Analisador.carregar(modelo)
    for t in textos[:AQUECIMENTO]:
        a.analisar(t)

    analisar = a.analisar
    relogio = time.perf_counter_ns
    tempos = []
    inicio = relogio()
    for t in textos:
        t0 = relogio()
        analisar(t)
        tempos.append(relogio() - t0)
    total_ns = relogio() - inicio

    inicio_lote = relogio()
    a.analisar_lote(textos)
    lote_ns = relogio() - inicio_lote

    tempos.sort()
    rss = pico_rss_bytes()
    return {
        "n_textos": len(textos),
        "max_caracteres": max(map(len, textos)) if textos else 0,
        "p50_us": _percentil(tempos, 50) / 1000,
        "p95_us": _percentil(tempos, 95) / 1000,
        "p99_us": _percentil(tempos, 99) / 1000,
        "max_us": tempos[-1] / 1000 if tempos else 0,
        "textos_por_s": len(textos) / (total_ns / 1e9) if total_ns else 0,
        "lote_textos_por_s": len(textos) / (lote_ns / 1e9) if lote_ns else 0,
        "pico_rss_mb": round(rss / (1024 * 1024), 1) if rss is not None else None,
        "python": sys.version.split()[0],
        "plataforma": sys.platform,
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--arquivo", help="textos reais, um por linha (UTF-8)")
    p.add_argument("-n", type=int, default=10_000, help="tamanho do corpus sintético (padrão: 10000)")
    p.add_argument("--modelo", help="diretório de artefatos")
    p.add_argument("--json", action="store_true", help="imprime o relatório em JSON")
    args = p.parse_args(argv)

    if args.arquivo:
        textos = [l for l in Path(args.arquivo).read_text(encoding="utf-8").splitlines() if l.strip()]
    else:
        textos = corpus_sintetico(args.n)

    r = executar(textos, args.modelo)
    if args.json:
        print(json.dumps(r))
        return 0
    rss = f"{r['pico_rss_mb']} MB" if r["pico_rss_mb"] is not None else "n/d"
    print(f"textos:          {r['n_textos']} (até {r['max_caracteres']} caracteres)")
    print(f"latência p50:    {r['p50_us']:.1f} µs")
    print(f"latência p95:    {r['p95_us']:.1f} µs   (meta: ≤ 1000 µs)")
    print(f"latência p99:    {r['p99_us']:.1f} µs")
    print(f"latência máx:    {r['max_us']:.1f} µs")
    print(f"throughput:      {r['textos_por_s']:,.0f} textos/s (1 thread, um a um)")
    print(f"throughput lote: {r['lote_textos_por_s']:,.0f} textos/s (analisar_lote)")
    print(f"pico de RSS:     {rss}   (meta: ≤ 100 MB)")
    print(f"python {r['python']} em {r['plataforma']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
