"""Os exemplos Python do README.md são executados como doctest."""

import doctest
import re
from pathlib import Path

README = Path(__file__).parent.parent / "README.md"


def test_exemplos_do_readme():
    blocos = re.findall(r"```python\n(.*?)```", README.read_text(encoding="utf-8"), flags=re.S)
    assert blocos, "README sem exemplos Python"
    teste = doctest.DocTestParser().get_doctest("\n\n".join(blocos), {}, "README.md", str(README), 0)
    runner = doctest.DocTestRunner(optionflags=doctest.NORMALIZE_WHITESPACE)
    runner.run(teste)
    resultado = runner.summarize(verbose=False)
    assert resultado.failed == 0 and resultado.attempted >= 5
