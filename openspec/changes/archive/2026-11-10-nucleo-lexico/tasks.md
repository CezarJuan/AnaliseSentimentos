# Tasks

## 1. Estrutura do pacote

- [x] 1.1 Criar `pyproject.toml` (Python ≥ 3.10, sem dependências de execução, `pytest` como extra `dev`, script `sentimento = sentimento.cli:main`, `recursos/*` como package data) e o esqueleto de `sentimento/` conforme design D1; verificar com `pip install -e .[dev]` e `python -c "import sentimento"`
- [x] 1.2 Criar `tests/` com `conftest.py` e registrar o marcador `bench` em `pyproject.toml` (excluído por padrão); verificar que `pytest` roda e coleta 0 testes sem erro

## 2. Pré-processamento (spec `preprocessamento-texto`)

- [x] 2.1 Implementar as etapas [a]–[d] do design D2 (URLs/menções, emoticons com borda, NFKC/lower/remoção de acentos, emojis Unicode e `<num>`), com regex compiladas na importação; verificar com testes dos cenários de normalização, placeholders e emojis/emoticons, incluindo `:D`, `XD` e uma URL que contém `:/`
- [x] 2.2 Implementar as etapas [e]–[f] (risadas → `<riso>`, alongamento 3+ → 1 com flag `alongado`); verificar com testes de `kkkkkkk`, `rsrsrs`, `hahaha`, `muuuuito` e `carro`
- [x] 2.3 Implementar as etapas [g]–[h] (tokenização com `<pont>`, `<excl>`, `<interr>` e abreviações por token inteiro); verificar com testes de `adorei!!!`, `ruim, caro`, `vc n vai` e de `n` dentro de palavra sem expansão
- [x] 2.4 Implementar a etapa [i] (escopo `NEG_` com parada em fronteira, negador e conectivo; limite de 3; placeholders e intensificadores imunes); verificar com testes de todos os cenários de "Escopo de negação" da spec
- [x] 2.5 Criar a tabela de regressão `tests/dados/preprocessamento.tsv` (≥ 40 pares texto → tokens, cobrindo cada etapa e texto vazio) e um teste que a percorre; verificar que o teste passa e que um teste de subprocesso confirma tokens idênticos em dois processos Python

## 3. Léxico e artefatos padrão

- [x] 3.1 Criar `sentimento/recursos/emojis.tsv` (≥ 40 emojis/emoticons pos/neg) e `config.json` (`versao`, `limiar_neutro`, `max_caracteres`) conforme design D4; verificar que os arquivos são UTF-8 válido e que o JSON é lido pelo carregador
- [x] 3.2 Curar `sentimento/recursos/lexico.tsv` semente (300–600 termos, incluindo gírias PT-BR e as entradas `<emo_pos>`, `<emo_neg>` e `<riso>`); verificar com um teste que carrega o arquivo sem duplicatas e com polaridades em [−1, 1], e checar o tamanho total dos recursos em ≤ 20 MB
- [x] 3.3 Implementar a carga de léxico/emojis/config (normalização dos termos, erro em duplicata, campos desconhecidos ignorados, mensagem que nomeia o arquivo faltante); verificar com testes de diretório válido, diretório sem `lexico.tsv` e léxico com duplicata

## 4. Classificação (spec `classificacao-sentimento`)

- [x] 4.1 Implementar `features_lexicas` conforme design D3 (inversão −0,8, peso do intensificador consumido pelo próximo termo do léxico e zerado em `<pont>`, contraste pelo último conectivo, `tanh(s/sqrt(n+1))`, registro de contribuições); verificar com testes dos cenários de negação, intensificador, contraste e riso/emoji
- [x] 4.2 Implementar `Analisador.carregar()` (padrão embutido via `importlib.resources` ou diretório; aviso se houver `W.npy`) e `analisar()` com truncamento em 5.000, rejeição de não-string, limiar ±0,15, confiança conforme D3 e campos `label`/`score`/`confianca`/`versao`/`modo`/`truncado`; verificar com testes de estrutura do resultado, texto vazio, neutro sem polaridade, texto de 6.000 caracteres e entrada `42`
- [x] 4.3 Implementar a explicação opcional (`explicar=True` → `tokens` com até 5 `{token, peso}` ordenados por |peso|; ausente por padrão); verificar com testes de `nao gostei do atendimento` e do campo ausente
- [x] 4.4 Implementar `analisar_lote()`; verificar com testes de lote equivalente às análises individuais, lote vazio e preservação de ordem
- [x] 4.5 Adicionar um teste de determinismo entre processos (subprocesso analisa os mesmos 100 textos e compara os JSONs campo a campo) e um teste de offline (bloquear `socket.socket` durante carga e análise); verificar que ambos passam
- [x] 4.6 Documentar o uso da API Python no `README.md` (instalação, `Analisador.carregar`, `analisar`, `analisar_lote`, `explicar`, campos da saída, limitações do modo léxico); verificar executando os exemplos do README como doctest ou script

## 5. CLI (spec `cli-sentimento`)

- [x] 5.1 Implementar `sentimento.cli.main` e `__main__.py` com argumento de texto, `--explicar`, `--modelo` e `--versao`, reconfiguração UTF-8 de stdin/stdout e `ensure_ascii=False`; verificar com testes via subprocesso de texto avulso, `--explicar`, `--versao` e `--modelo pasta_inexistente` (código 2)
- [x] 5.2 Implementar o modo JSONL pela stdin (eco de `id`, linhas em branco ignoradas, linha inválida → `{"erro", "linha"}`, código final 1 se houve erro); verificar com testes via subprocesso dos cenários da spec, incluindo entrada com "ótimo 😍"
- [x] 5.3 Documentar a CLI no `README.md` (exemplos de texto avulso e de pipeline JSONL, códigos de saída); verificar executando os comandos documentados

## 6. Benchmark e verificação integrada

- [x] 6.1 Implementar `bench/benchmark.py` conforme design D7 (corpus sintético com seed fixa, `--arquivo`, aquecimento, p50/p95/p99, textos/s, pico de RSS ou "n/d"); verificar que `python bench/benchmark.py` imprime o relatório completo
- [x] 6.2 Adicionar o teste `pytest -m bench` que falha se p95 > 1 ms ou RSS > 100 MB, e documentar no `README.md` como rodar o benchmark; verificar rodando `pytest -m bench` na máquina-alvo e registrando os números obtidos
- [x] 6.3 Rodar a suíte completa (`pytest`) e `openspec validate nucleo-lexico --strict`; verificar que ambos passam sem falhas

## Workflow follow-up

- Revisar os números do benchmark: se o throughput ficar muito abaixo de 10.000 textos/s, registrar isso como entrada para a change do modelo treinado.
- Arquivar a change após a revisão (`/opsx:archive`).
