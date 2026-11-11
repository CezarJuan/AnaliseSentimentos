# Proposal

## Why

O núcleo léxico (change `nucleo-lexico`) já classifica textos, mas só pela linha de comando e pela API Python. Para experimentar o classificador, ver por que ele decidiu algo e processar um arquivo de textos, hoje é preciso escrever JSON à mão. A spec original prevê uma interface web local (RF6) com análise ao vivo, explicação visual e modo lote, funcionando offline. Como a interface consome a mesma saída da API, ela pode ser construída já, sobre o modo léxico, e continuará valendo quando o modelo treinado chegar.

## What Changes

- Novo subcomando `sentimento serve [--porta N] [--modelo DIR]`, que sobe um servidor HTTP local só com a biblioteca padrão, escutando apenas em `127.0.0.1`.
- API local em JSON: `POST /api/analisar`, `POST /api/lote` (até 10.000 textos), `GET /api/saude` (versão, modo e latência p95 recente).
- Página única em HTML, CSS e JavaScript puro, embutida no pacote (≤ 100 KB, sem build, framework nem CDN), com:
  - análise ao vivo com debounce, Ctrl+Enter para forçar e cancelamento de requisições antigas;
  - rótulo com ícone e texto, confiança, latência e barra de score de −1 a +1;
  - destaque dos tokens que mais pesaram, com marca de negação;
  - modo lote: upload de `.txt` ou `.csv`, tabela de resultados e download em CSV;
  - histórico das últimas 20 análises, só em memória;
  - rodapé com versão e modo;
  - tema claro e escuro, navegação por teclado e contraste AA.
- Proteções de servidor local: bind fixo em loopback, validação do cabeçalho `Host` (contra DNS rebinding), exigência de `Content-Type: application/json` (contra POST de outros sites), CSP restrita e nenhum texto em log ou disco.
- **BREAKING (menor)**: `sentimento serve` passa a ser um subcomando. Analisar a palavra literal "serve" como texto exige `sentimento -- serve` ou a entrada JSONL.

Fora do escopo: a opção com FastAPI + uvicorn citada na spec original (fica para quando houver necessidade de concorrência real), autenticação, acesso por outras máquinas da rede, persistência de histórico e o modo modelo (que a interface só exibe se existir).

## Capabilities

### New Capabilities

- `api-local`: servidor HTTP local e suas rotas JSON (analisar, lote, saúde, página estática), incluindo limites, erros, latência de ida e volta e as proteções de rede e privacidade.
- `interface-web`: a página servida em `/`: comportamento da análise ao vivo, apresentação do resultado, destaque de tokens, modo lote, histórico, rodapé, acessibilidade e funcionamento offline.

### Modified Capabilities

(nenhuma; as capabilities `classificacao-sentimento` e `cli-sentimento` da change `nucleo-lexico` ainda não foram arquivadas para `openspec/specs/`. O subcomando `serve` fica especificado em `api-local`, para não criar dependência de um delta ainda não arquivado.)

## Impact

- Código novo: `sentimento/servidor.py` e os estáticos em `sentimento/web/` (`index.html`, `app.js`, `estilo.css`), mais testes em `tests/` e testes de JavaScript em `tests/js/`.
- `sentimento/cli.py`: o subcomando `serve` é despachado antes do parser atual, e o resto do comportamento não muda.
- `pyproject.toml`: `web/*` entra como package data.
- Dependências: nenhuma nova em tempo de execução. Os testes de JavaScript usam o Node (`node --test`) se ele estiver instalado, e são pulados caso contrário.
