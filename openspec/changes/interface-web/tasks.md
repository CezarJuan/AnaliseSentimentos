# Tasks

## 1. Servidor e rotas da API (spec `api-local`)

- [x] 1.1 Criar `sentimento/servidor.py` com `criar_servidor(analisador, porta)` sobre `ThreadingHTTPServer` em `127.0.0.1` (design D1) e uma fixture de teste que sobe o servidor numa porta livre em thread; verificar com um teste que confere `server_address[0] == "127.0.0.1"` e que o servidor encerra limpo
- [x] 1.2 Implementar `POST /api/analisar` (resultado + `latencia_ms`, `explicar` opcional) e `POST /api/lote` (`{"resultados": [...]}`, limite de 10.000 → 413, validação de todos os itens antes de analisar); verificar com testes dos cenários de análise com/sem explicação, lote equivalente às análises individuais e lote de 10.001
- [x] 1.3 Implementar `GET /api/saude` com janela de 1.000 latências protegida por lock (p95 ou `null`); verificar com testes antes e depois de 10 análises
- [x] 1.4 Implementar as respostas de erro em JSON (400 JSON inválido/tipo errado, 404, 405, 413 corpo > 16 MB, 415 Content-Type) e a validação de `Host` (403); verificar com um teste por código, incluindo `Host: site-malicioso.com:<porta>` e POST `text/plain`
- [x] 1.5 Implementar os cabeçalhos de segurança (CSP, nosniff, `Cache-Control: no-store` na API, nenhum CORS) e o log sem corpo (`MÉTODO /rota STATUS ms`); verificar com testes dos cabeçalhos em `/` e na API, de `OPTIONS` com `Origin` sem `Access-Control-Allow-Origin` e de log capturado sem o texto "segredo123"
- [x] 1.6 Adicionar testes de concorrência (8 clientes em paralelo, cada um recebe o próprio resultado) e de ida e volta (500 requisições sequenciais, p95 ≤ 50 ms); verificar que ambos passam

## 2. Subcomando `serve` na CLI

- [x] 2.1 Despachar `serve` em `sentimento/cli.py` antes do parser atual (design D9), com `--porta` (padrão 8080) e `--modelo`, imprimindo `http://127.0.0.1:<porta>/`, erro com código 2 para porta ocupada ou modelo inválido e saída 0 com Ctrl+C; verificar com testes via subprocesso (URL impressa e servidor respondendo, porta ocupada, modelo inexistente) e um teste de que `sentimento -- serve` analisa a palavra como texto
- [x] 2.2 Garantir que os testes atuais da CLI (`tests/test_cli.py`) continuam passando sem alteração; verificar rodando `pytest tests/test_cli.py`

## 3. Lógica pura do front end (`sentimento/web/logica.js`)

- [x] 3.1 Criar `logica.js` (módulo ES sem DOM) com `debounce`, `normalizarPalavra` (NFD, sem `\p{Mn}`, minúsculas, alongamento, abreviações) e `destacar(texto, tokens)`, que devolve trechos `{texto, peso?, negado?}`; verificar com `tests/js/logica.test.mjs` cobrindo "nao gostei do atendimento", "Ótimooo produto", tokens sem palavra correspondente e palavras repetidas
- [x] 3.2 Adicionar o parser CSV RFC 4180 (aspas, aspas duplicadas, vírgulas e quebras de linha em campos, BOM, coluna `texto` ou primeira coluna), a leitura de `.txt`, a divisão em partes (≤ 10.000 itens e ~8 MB) e a geração de CSV de saída (escape RFC 4180, proteção contra fórmula, BOM); verificar com testes do Node para cada caso, incluindo 25.000 linhas → 3 partes
- [x] 3.3 Criar `tests/test_js.py`, que roda `node --test tests/js/` (pulado se não houver Node), e o teste de paridade que compara `normalizarPalavra` com o pré-processamento Python numa lista de ≥ 30 palavras (acentos, alongamento, abreviações); verificar com `pytest tests/test_js.py`

## 4. Página (`index.html`, `estilo.css`, `app.js`)

- [x] 4.1 Criar `index.html` e `estilo.css` com landmarks, campo de texto, botão Analisar, área de resultado (`aria-live`, barra `role="meter"`), lista de tokens, seção de lote, histórico, rodapé e botão de tema; tokens de cor em `:root` com tema escuro por `prefers-color-scheme` e `data-theme`, foco visível; sem script ou estilo inline. Verificar com um teste Python que a página não referencia URLs externas nem contém `<script>`/`style=` inline
- [x] 4.2 Criar `app.js` com análise ao vivo (debounce de 150 ms, Ctrl/Cmd+Enter, campo vazio limpa), `AbortController` + checagem de sequência (design D5), renderização do resultado (rótulo, ícone, cor, confiança %, latência, barra) e destaque via `logica.destacar` usando só `textContent`; verificar manualmente no navegador os cenários de "Análise ao vivo", "Descarte de resultados desatualizados", "Apresentação do resultado" e "Destaque de tokens"
- [x] 4.3 Implementar no `app.js` o modo lote (upload `.txt`/`.csv`, erro para outras extensões, envio em partes com progresso, tabela limitada a 1.000 linhas com aviso, download CSV), o histórico (20 itens confirmados, limpar, clique recoloca o texto), o rodapé via `/api/saude` com aviso de servidor fora do ar e o botão de tema com `localStorage` só para o tema; verificar manualmente os cenários de "Modo lote por arquivo", "Histórico da sessão" e "Rodapé de status"
- [x] 4.4 Servir os estáticos por tabela fixa via `importlib.resources`, adicionar `web/*` ao package data e um teste de que `GET /`, `/app.js`, `/logica.js` e `/estilo.css` respondem com o content-type correto e somam ≤ 100 KB; verificar com `pytest` e com `pip install .` num venv temporário, servindo a página a partir do pacote instalado

## 5. Documentação e verificação integrada

- [x] 5.1 Documentar no `README.md` a interface web (`sentimento serve`, porta, o que a página faz, rotas da API com exemplos e a nota de `sentimento -- serve`); verificar executando os exemplos de `curl`/PowerShell do README contra o servidor
- [ ] 5.2 Criar `tests/roteiro_manual_web.md` com o passo a passo de verificação no navegador (teclado, temas claro/escuro, contraste, offline com a rede desligada, armazenamento do navegador só com o tema) e executá-lo em Chrome ou Edge e Firefox; verificar registrando o resultado de cada passo no próprio roteiro
- [ ] 5.3 Rodar a suíte completa (`pytest`, incluindo `tests/test_js.py`) e `openspec validate interface-web --strict`; verificar que ambos passam

## Workflow follow-up

- Arquivar `nucleo-lexico` antes desta change (`/opsx:archive nucleo-lexico`), para que as specs-base existam em `openspec/specs/`.
- Arquivar esta change após a revisão (`/opsx:archive interface-web`).
