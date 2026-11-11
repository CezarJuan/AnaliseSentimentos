# Design

## Context

Hoje existe o pacote `sentimento` (change `nucleo-lexico`), com `Analisador.carregar/analisar/analisar_lote` e uma CLI baseada em `argparse`, com texto posicional opcional e as opções `--explicar`, `--modelo` e `--versao`. A análise de um texto curto leva ~200 µs no p95, e o pacote não tem dependências de execução. A motivação está em proposal.md, e os comportamentos exigidos estão nas specs `api-local` e `interface-web`.

## Goals / Non-Goals

**Goals:**
- Servidor e página sem nenhuma dependência nova, e que funcionem a partir do pacote instalado.
- Lógica do front end testável sem navegador (funções puras separadas do DOM).
- Manter intacta a superfície atual da CLI, exceto pela palavra `serve`.

**Non-Goals:**
- Desempenho sob carga alta ou muitos usuários: é uma ferramenta de uma pessoa, na própria máquina.
- Compatibilidade com navegadores antigos: o alvo são as versões atuais de Chrome, Edge, Firefox e Safari (ES2020, `AbortController`, `fetch`).
- Teste automatizado de navegador (Playwright e similares): exigiria dependência pesada. A verificação visual fica num roteiro manual.

## Decisions

### D1. Servidor: `ThreadingHTTPServer` da biblioteca padrão

```
 navegador (127.0.0.1:8080)
     |
     v
 ThreadingHTTPServer(("127.0.0.1", porta), Manipulador)
     |  1 thread por conexao (daemon_threads = True)
     v
 Manipulador.do_GET / do_POST / do_OPTIONS ...
     |-- valida Host          -> 403
     |-- roteia               -> 404 / 405
     |-- valida Content-Type  -> 415   (POST)
     |-- le corpo <= 16 MB    -> 413
     |-- json.loads           -> 400
     v
 Analisador (compartilhado, somente leitura)  +  JanelaLatencias (com lock)
```

- O `Analisador` não tem estado mutável depois de carregado (dicts lidos e regex compiladas), então uma única instância pode ser compartilhada entre threads sem lock. Com o GIL, a análise roda em série, mas cada uma leva ~0,2 ms, o que basta.
- A janela de latências é um `collections.deque(maxlen=1000)`, protegida por `threading.Lock`. O p95 é calculado sob demanda em `/api/saude`.
- Alternativa descartada: FastAPI + uvicorn. Seria mais rápido sob concorrência, mas adiciona dependências e não muda nada para uma pessoa só. Fica como opção futura, mantendo as mesmas rotas.
- O bind é sempre em `127.0.0.1`, sem opção `--host`. O teste de "outra interface" verifica `server_address[0] == "127.0.0.1"`, em vez de tentar uma conexão de outra máquina.
- `allow_reuse_address` usa o padrão do `http.server`. A porta ocupada é detectada pelo `OSError` no bind e vira a mensagem de erro com código 2.

### D2. Proteções de servidor local

- **Host**: aceita `127.0.0.1:<porta>` e `localhost:<porta>`. Isso bloqueia DNS rebinding: um site malicioso que aponta seu domínio para 127.0.0.1 envia `Host: malicioso.com`.
- **Content-Type obrigatório** `application/json` (parâmetros como `; charset=utf-8` são aceitos): um formulário HTML de outro site só consegue enviar `text/plain`, `multipart/form-data` ou `x-www-form-urlencoded` sem preflight. Já `application/json` cross-origin dispara um preflight CORS, que o servidor não aprova (não envia `Access-Control-Allow-*`). Isso fecha o CSRF sem precisar de token.
- **CSP**: `default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'`. Não há scripts nem estilos inline, então tudo fica em arquivos.
- **Log**: `log_message` é sobrescrito para escrever `MÉTODO /rota STATUS duração_ms` na saída de erro. O corpo nunca é registrado. A query string também não é registrada.

### D3. Formato das respostas

- `/api/analisar` devolve o resultado da API Python mais `latencia_ms`, que é o tempo de processamento no servidor, medido com `perf_counter`, e não a ida e volta. A ida e volta é medida pela página.
- `/api/lote` devolve `{"resultados": [...]}`, e não uma lista crua. Um objeto deixa espaço para metadados futuros (por exemplo `latencia_ms` total) sem quebrar clientes. A validação de tipos acontece antes de analisar qualquer item: um item que não seja string gera 400, com o índice na mensagem.
- `/api/saude`: `{"versao", "modo", "latencia_p95_ms"}`.
- O JSON sai com `ensure_ascii=False` e `Content-Type: application/json; charset=utf-8`.

### D4. Estáticos e empacotamento

```
sentimento/web/
  index.html     # estrutura e landmarks; sem inline script/style
  estilo.css     # tokens de cor em :root, tema escuro, foco visível
  app.js         # módulo ES: DOM, eventos, fetch
  logica.js      # módulo ES puro: debounce, CSV, normalização, destaque, partes de lote
```

- São servidos por uma tabela fixa `{rota: (arquivo, content-type)}`, lida com `importlib.resources`. Não há servidor de arquivos genérico, então não existe risco de path traversal.
- `logica.js` não toca no DOM nem em `fetch`, e é importado por `app.js` e pelos testes do Node.
- `pyproject.toml` ganha `web/*` em package data. Um teste soma os tamanhos e falha acima de 100 KB.

### D5. Análise ao vivo e corrida de respostas

```
 tecla -> limpa timer -> timer 150ms --+
 Ctrl+Enter ---------------------------+--> analisar(texto, {confirmar})
                                            |
                                            |  controlador_anterior.abort()
                                            |  id = ++seq ; t0 = performance.now()
                                            v
                                         fetch(..., {signal})
                                            |
                         resposta: se id != seq ou texto != campo.value -> descarta
                                   senao renderiza ; se confirmar -> historico
```

Duas defesas, de propósito. O `abort()` economiza trabalho. A checagem `id == seq` garante a regra mesmo quando a resposta chega antes do abort ter efeito. `AbortError` é ignorado silenciosamente. Erro de rede mostra "servidor não está respondendo" e mantém o último resultado esmaecido.

### D6. Destaque de tokens no texto original

A API devolve tokens normalizados (`otimo`, `NEG_gostei`, `<emo_pos>`), e não posições no texto. Em vez de mudar a API Python para devolver offsets (o que mexeria no contrato do pré-processamento), a página faz uma correspondência aproximada:

1. Divide o texto original em palavras com `/[\p{L}\p{N}_]+/gu`, guardando as posições.
2. Normaliza cada palavra como o servidor faz: NFD, remoção de `\p{Mn}`, minúsculas e redução de 3+ letras repetidas a 1, e expande o mesmo dicionário de abreviações (replicado em `logica.js`, com teste que compara com o Python).
3. Se a forma normalizada coincide com o token sem o prefixo `NEG_`, a palavra é sublinhada com a cor e o sinal do peso, e recebe a marca "negado" quando o token tinha `NEG_`.

Placeholders (`<emo_pos>`, `<riso>`, etc.) não têm palavra correspondente e aparecem só na lista. O texto é montado com `textContent` e elementos `<mark>`, nunca com `innerHTML`, para não abrir espaço a XSS com o texto do usuário.

Alternativa descartada: offsets vindos do servidor. Seria exato, mas exige rastrear posições através de 9 etapas que reescrevem a string. Fica como evolução, se a aproximação se mostrar insuficiente.

Teste de paridade: um teste em Python roda `logica.js` no Node com uma lista de palavras e compara com `normalizar()` + alongamento + `ABREVIACOES` do Python.

### D7. Modo lote

- `.txt`: divide por `\r?\n` e descarta linhas em branco. `.csv`: parser RFC 4180 próprio em `logica.js` (aspas, aspas duplicadas, vírgulas e quebras de linha dentro de campos, BOM). Se a primeira linha tiver a coluna `texto` (comparação sem caixa e sem espaços), usa essa coluna e pula o cabeçalho; senão, usa a primeira coluna de todas as linhas.
- Outras extensões: erro na página, sem requisição.
- O envio é feito em partes de 10.000, em sequência, com progresso "parte 2 de 3". Os resultados são concatenados na ordem.
- A tabela renderiza no máximo 1.000 linhas, com aviso "mostrando 1.000 de N". O CSV baixado tem todas. Isso evita travar a página com 25.000 linhas no DOM.
- O download gera um `Blob` com BOM UTF-8 (para o Excel abrir com acentos) e `URL.createObjectURL`. Os campos são escapados conforme o RFC 4180, e campos que começam com `=`, `+`, `-` ou `@` ganham um `'` na frente, para evitar injeção de fórmula ao abrir no Excel. Isso não se aplica aos campos numéricos `score` e `confianca`, que são gerados pelo próprio sistema.

### D8. Histórico, tema e acessibilidade

- Histórico: array em memória com no máximo 20 itens, o mais novo primeiro. Entra nele só a análise confirmada (Ctrl+Enter ou botão). Um clique num item recoloca o texto no campo.
- Tema: `prefers-color-scheme` por padrão. O botão alterna `data-theme` no `<html>`, e só essa preferência vai para `localStorage`, com try/catch.
- Ícones: caracteres de texto (`▲`, `▼` e `●`) com `aria-hidden`, junto do rótulo escrito. As cores dos tokens foram verificadas para 4,5:1 nos dois temas, e o sinal "+"/"−" acompanha sempre a cor.
- A barra de score usa `role="meter"` com `aria-valuemin="-1"`, `aria-valuemax="1"` e `aria-valuenow`. O resultado fica numa região `aria-live="polite"`.

### D9. Subcomando na CLI

`main(argv)` verifica se `argv[0] == "serve"` antes do parser atual. Se for, delega a um parser próprio (`--porta`, `--modelo`). Caso contrário, segue igual. `sentimento -- serve` funciona porque `argv[0]` é `--`, o que cai no parser atual, e o `argparse` trata o que vem depois de `--` como posicional. Isso evita converter a CLI inteira em subparsers, o que quebraria `sentimento "texto"`.

## Risks / Trade-offs

- [O destaque aproximado pode sublinhar a palavra errada quando ela se repete] → o destaque marca todas as ocorrências da forma normalizada. Isso é aceitável, porque o peso vale para o token, e a lista exata está ao lado.
- [Abreviações duplicadas em JS e Python podem divergir] → o teste de paridade falha se divergirem.
- [`ThreadingHTTPServer` com o GIL serializa a análise] → com ~0,2 ms por texto, o gargalo é o JSON do lote. Um lote de 10.000 textos deve levar ~1–2 s, mostrado com progresso.
- [Corpo de 16 MB com 10.000 textos de 5.000 caracteres pode passar do limite] → 10.000 × 5.000 caracteres ≈ 50 MB no pior caso. A página divide por tamanho também: uma parte fecha ao atingir 10.000 itens ou ~8 MB de JSON, o que vier primeiro.
- [Mudança na CLI: `sentimento serve` deixa de analisar a palavra "serve"] → documentado no README e na ajuda (`sentimento -- serve`).
- [Porta 8080 frequentemente ocupada] → mensagem clara sugerindo `--porta`.

## Open Questions

- Se o servidor deve abrir o navegador automaticamente (`webbrowser.open`) ao subir. É conveniência, que pode virar uma flag `--abrir` depois sem mudar nenhuma spec.
