# Proposal

## Why

A spec "Análise de Sentimentos Local de Baixa Latência" descreve um sistema completo (pré-processamento, léxico, regressão logística, treino, CLI e front end), mas o projeto ainda não tem nenhum código. O núcleo léxico (pré-processamento + score léxico + modo fallback) é a base de todo o resto: o modelo treinado reaproveita o mesmo pré-processamento e as mesmas features léxicas, e a interface consome a mesma saída. Entregar esse núcleo primeiro dá um classificador utilizável no "dia 1", sem dados de treino, e fixa o contrato de pré-processamento antes que o treino passe a depender dele.

## What Changes

- Novo pacote Python `sentimento`, instalável, com a classe `Analisador` e a CLI `sentimento`.
- Pipeline de pré-processamento determinístico para PT-BR informal: normalização, placeholders (`<url>`, `<user>`, `<num>`), emojis/emoticons, risadas, alongamentos, abreviações, tokenização, negação, intensidade e contraste.
- Classificação só pelo léxico (o "modo fallback" da spec original), com saída estruturada `label`, `score`, `confianca`, `versao`, `modo` e `truncado`, e explicação opcional (top 5 tokens).
- Artefatos padrão embutidos no pacote: `lexico.tsv` semente revisado à mão, `emojis.tsv` e `config.json`.
- Script de benchmark de latência (p50/p95/p99) e throughput.
- Correções de contradições encontradas na spec original, decididas aqui (detalhes em design.md):
  - a tokenização passa a emitir fronteiras de pontuação, para que o escopo da negação termine nela;
  - intensificadores e atenuadores não recebem o prefixo `NEG_`;
  - os limiares do fallback (±0,15) passam a valer para o score normalizado (após `tanh`);
  - emoticons são tratados antes da conversão para minúsculas;
  - risadas (`kkk`, `rsrs`, `haha`) são tratadas antes da redução de alongamentos.

Fora do escopo desta change (ficam para changes seguintes): regressão logística, hashing de n-gramas, pipeline de treino e avaliação de macro-F1, servidor local e front end web.

## Capabilities

### New Capabilities

- `preprocessamento-texto`: transforma texto bruto em PT-BR informal numa sequência de tokens normalizados e anotados (negação, placeholders, emojis, risadas). Contrato compartilhado entre inferência e o treino futuro.
- `classificacao-sentimento`: classifica um texto ou um lote em positivo/negativo/neutro com score de −1 a +1, confiança, explicação opcional, limites de entrada, determinismo e metas de latência.
- `cli-sentimento`: interface de linha de comando para analisar um texto avulso ou um fluxo JSONL pela stdin.

### Modified Capabilities

(nenhuma; o projeto ainda não tem specs)

## Impact

- Código novo: pacote `sentimento/` (módulos de pré-processamento, léxico, analisador e CLI), recursos em `sentimento/recursos/`, testes em `tests/`, script em `bench/`.
- Dependências: Python 3.10+ só com a biblioteca padrão em tempo de execução; `pytest` em desenvolvimento. O NumPy entra quando chegar o modelo treinado (change seguinte).
- Nenhuma API de rede e nenhuma escrita em disco durante a análise.
