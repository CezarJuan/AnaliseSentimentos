"""Metas de latência e memória (spec `classificacao-sentimento`).

Fora da suíte padrão: rode com `pytest -m bench` na máquina-alvo.
Roda em subprocesso para que a memória medida não inclua o pytest.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

BENCH = Path(__file__).parent.parent / "bench" / "benchmark.py"


@pytest.mark.bench
def test_latencia_e_memoria():
    r = subprocess.run([sys.executable, str(BENCH), "--json"], capture_output=True, check=True, timeout=600)
    relatorio = json.loads(r.stdout)
    print("\n" + json.dumps(relatorio, indent=2))
    assert relatorio["n_textos"] >= 10_000
    assert relatorio["max_caracteres"] <= 280
    assert relatorio["p95_us"] <= 1000, f"p95 de {relatorio['p95_us']} µs passa da meta de 1 ms"
    if relatorio["pico_rss_mb"] is not None:
        assert relatorio["pico_rss_mb"] <= 100, f"pico de RSS de {relatorio['pico_rss_mb']} MB passa de 100 MB"
