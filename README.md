# sentimento

Análise de sentimentos local e de baixa latência para português do Brasil.

Classifica um texto curto como **positivo**, **negativo** ou **neutro**, com um score contínuo de −1 a +1. Roda 100% local, em CPU, sem chamadas de rede e só com a biblioteca padrão do Python.

> **Versão 0.1 — modo léxico.** A decisão vem de um léxico de polaridade com regras de negação, intensidade e contraste. O modelo treinado (regressão logística) chega numa versão futura, com a mesma API e o mesmo formato de saída.

## Instalação

Requer Python 3.10+.

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate    Linux/macOS: source .venv/bin/activate
pip install -e ".[dev]"
```

## API Python

```python
>>> from sentimento import Analisador
>>> a = Analisador.carregar()          # artefatos embutidos; ou Analisador.carregar("modelo/")
>>> a.analisar("o produto chegou rapido, adorei!")
{'label': 'positivo', 'score': 0.4298, 'confianca': 0.4298, 'versao': '0.1.0', 'modo': 'lexico', 'truncado': False}
```

Com `explicar=True`, o resultado inclui até 5 tokens com maior contribuição ao score. Tokens com prefixo `NEG_` estavam no escopo de uma negação:

```python
>>> a.analisar("nao gostei do atendimento, mas o preco e otimo", explicar=True)["tokens"]
[{'token': 'otimo', 'peso': 1.2}, {'token': 'NEG_gostei', 'peso': -0.28}]
```

Em lote, a ordem e o tamanho da lista são preservados:

```python
>>> [r["label"] for r in a.analisar_lote(["amei 😍", "pessimo, nunca mais", "chegou na terca"])]
['positivo', 'negativo', 'neutro']
```

Para inspecionar o pré-processamento:

```python
>>> a.preprocessar("vc n vai gostar mt :(").tokens
('voce', 'nao', 'NEG_vai', 'NEG_gostar', 'muito', '<emo_neg>')
```

### Campos da saída

| Campo | Tipo | Significado |
| --- | --- | --- |
| `label` | str | `positivo` (score > 0,15), `negativo` (score < −0,15) ou `neutro` |
| `score` | float | De −1 a +1, com 4 casas decimais |
| `confianca` | float | De 0 a 1. Positivo/negativo: \|score\|. Neutro: 1 − \|score\|/0,15. Texto sem tokens: 0 |
| `versao` | str | Versão dos artefatos (`config.json`) |
| `modo` | str | `lexico` nesta versão |
| `truncado` | bool | `True` se o texto passou de 5.000 caracteres e foi cortado |
| `tokens` | list | Só com `explicar=True`: `{token, peso}`, ordenados por \|peso\| |

Erros: uma entrada que não é `str` gera `TypeError`. Um diretório de artefatos inválido gera `sentimento.ErroArtefato`, com uma mensagem que nomeia o arquivo faltante ou malformado.

### Artefatos

`Analisador.carregar(dir)` lê de `dir` os arquivos `lexico.tsv` (`termo<TAB>polaridade`), `emojis.tsv` (`simbolo<TAB>pos|neg`) e `config.json`. Os padrões ficam em `sentimento/recursos/`. Na carga, os termos do léxico são normalizados (minúsculas, sem acento).

## Linha de comando

Um texto como argumento gera uma linha JSON:

```bash
$ sentimento "adorei o produto"
{"label": "positivo", "score": 0.4219, "confianca": 0.4219, "versao": "0.1.0", "modo": "lexico", "truncado": false}

$ sentimento --explicar "nao gostei"
{"label": "negativo", "score": -0.3125, "confianca": 0.3125, "versao": "0.1.0", "modo": "lexico", "truncado": false, "tokens": [{"token": "NEG_gostei", "peso": -0.56}]}
```

Sem texto, a CLI lê JSONL da entrada padrão (um objeto `{"texto": ..., "id": opcional}` por linha) e escreve um JSON por linha, na mesma ordem e repetindo o `id`:

```bash
$ printf '{"id": 1, "texto": "adorei"}\n{"id": 2, "texto": "pessimo"}\n' | sentimento
{"id": 1, "label": "positivo", "score": 0.5624, "confianca": 0.5624, "versao": "0.1.0", "modo": "lexico", "truncado": false}
{"id": 2, "label": "negativo", "score": -0.5624, "confianca": 0.5624, "versao": "0.1.0", "modo": "lexico", "truncado": false}

$ sentimento < entrada.jsonl > saida.jsonl
```

Uma linha inválida (JSON malformado, ou sem `texto` do tipo string) gera `{"linha": N, "erro": "..."}` e não interrompe as demais.

| Opção | Efeito |
| --- | --- |
| `--explicar` | Inclui o campo `tokens` |
| `--modelo DIR` | Carrega os artefatos de `DIR` |
| `--versao` | Imprime a versão dos artefatos e sai |

**Códigos de saída:** `0` ok; `1` alguma linha JSONL inválida; `2` erro de uso ou de artefatos (a mensagem vai para a saída de erro).

A entrada e a saída são sempre UTF-8, inclusive no Windows. Um BOM no início da entrada é ignorado, e acentos e emojis saem sem escapes. `python -m sentimento` é equivalente a `sentimento`.

## Interface web

```bash
sentimento serve                 # http://127.0.0.1:8080/
sentimento serve --porta 9000 --modelo modelo/
```

Abra a URL impressa no navegador. A página:

- analisa enquanto você digita (150 ms após a última tecla). <kbd>Ctrl</kbd>+<kbd>Enter</kbd> analisa na hora e salva no histórico;
- mostra o rótulo (texto, ícone e cor), a confiança, a latência de ida e volta e uma barra de −1 a +1;
- destaca as palavras que mais pesaram (verde/+ positivo, vermelho/− negativo, ondulado/¬ negado);
- processa arquivos `.txt` (um texto por linha) ou `.csv` (coluna `texto`, ou a primeira coluna; aceita `,` ou `;`) e baixa o resultado em CSV;
- guarda as últimas 20 análises confirmadas só em memória. Recarregar a página apaga tudo;
- tem tema claro e escuro (segue o sistema; o botão no rodapé alterna).

O servidor escuta **só em `127.0.0.1`**: não é acessível por outras máquinas, não grava textos em disco nem em log e não faz chamadas de rede. Ctrl+C encerra.

> `serve` é um subcomando. Para analisar a palavra "serve" como texto, use `sentimento -- serve`.

### API local

| Método | Rota | Corpo → resposta |
| --- | --- | --- |
| POST | `/api/analisar` | `{"texto": "...", "explicar": true}` → resultado + `latencia_ms` (+ `tokens`) |
| POST | `/api/lote` | `{"textos": [...], "explicar": false}` → `{"resultados": [...]}`, até 10.000 textos |
| GET | `/api/saude` | `{"versao", "modo", "latencia_p95_ms"}` |
| GET | `/` | a página |

As rotas POST exigem `Content-Type: application/json`. Os erros vêm como `{"erro": "..."}`: 400 (JSON ou campo inválido), 403 (`Host` diferente de `127.0.0.1`/`localhost`), 404, 405, 413 (corpo > 16 MB ou lote > 10.000) e 415 (Content-Type).

```bash
curl -s -X POST http://127.0.0.1:8080/api/analisar \
     -H "Content-Type: application/json" -d '{"texto": "adorei", "explicar": true}'
curl -s http://127.0.0.1:8080/api/saude
```

No PowerShell:

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8080/api/lote `
  -ContentType "application/json; charset=utf-8" `
  -Body ([Text.Encoding]::UTF8.GetBytes('{"textos": ["ótimo", "péssimo"]}'))
```

## Testes e benchmark

```bash
pytest                                  # suíte padrão (sem benchmark)
pytest -m bench -s                      # metas: p95 ≤ 1 ms por texto e pico de RSS ≤ 100 MB
python bench/benchmark.py               # relatório: p50/p95/p99, textos/s, pico de RSS
python bench/benchmark.py --arquivo textos.txt   # textos reais, um por linha
```

O corpus padrão tem 10.000 textos sintéticos de até 280 caracteres, gerados com seed fixa. Antes de tratar os números como definitivos, confirme a meta de latência com textos reais (`--arquivo`).

Referência (Windows 11, Python 3.11, 1 thread): p50 ≈ 108 µs, p95 ≈ 197 µs, p99 ≈ 213 µs, ~9.200 textos/s e pico de RSS de ~29 MB.

## Limitações do modo léxico

- O léxico semente tem cerca de 480 termos. Palavras fora dele não pesam, então textos com vocabulário diferente tendem a sair como `neutro`.
- Ironia e sarcasmo ("que ótimo, atrasou de novo") saem como positivo.
- Sentimento misto vira um único rótulo, e textos longos diluem o score.
- A negação alcança no máximo 3 tokens e termina na pontuação.
- Só português; outros idiomas saem quase sempre como `neutro`.
