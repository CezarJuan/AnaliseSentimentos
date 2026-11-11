# Spec Delta

## Purpose

Expor o analisador de sentimentos por HTTP apenas na máquina local, com rotas JSON para análise individual, em lote e de saúde, servindo também a página da interface web, sem rede externa e sem guardar textos.

## ADDED Requirements

### Requirement: Subcomando serve
O comando `sentimento serve` SHALL iniciar o servidor local na porta 8080 por padrão, ou na porta de `--porta N`, carregando artefatos de `--modelo DIR` quando informado, e SHALL imprimir na saída padrão a URL de acesso. Ctrl+C SHALL encerrar o servidor com código de saída 0.

#### Scenario: Porta padrão
- **WHEN** o usuário executa `sentimento serve`
- **THEN** a saída mostra `http://127.0.0.1:8080/` e o servidor responde nessa URL

#### Scenario: Porta ocupada
- **WHEN** o usuário executa `sentimento serve --porta 8080` com a porta já em uso
- **THEN** uma mensagem de erro que cita a porta vai para a saída de erro e o código de saída é 2

#### Scenario: Diretório de modelo inválido
- **WHEN** o usuário executa `sentimento serve --modelo pasta_inexistente`
- **THEN** o servidor não sobe, uma mensagem de erro vai para a saída de erro e o código de saída é 2

#### Scenario: Texto literal "serve"
- **WHEN** o usuário executa `sentimento -- serve`
- **THEN** a palavra "serve" é analisada como texto, como em qualquer outro texto avulso

### Requirement: Escuta só em loopback
O servidor SHALL escutar exclusivamente em `127.0.0.1` e SHALL NOT oferecer opção para escutar em outra interface.

#### Scenario: Acesso por outra interface
- **WHEN** o servidor está rodando e outra máquina da rede tenta conectar ao IP da máquina na mesma porta
- **THEN** a conexão é recusada

### Requirement: Validação do cabeçalho Host
O servidor SHALL responder 403 a qualquer requisição cujo cabeçalho `Host` não seja `127.0.0.1:<porta>` ou `localhost:<porta>`.

#### Scenario: DNS rebinding
- **WHEN** chega uma requisição com `Host: site-malicioso.com:8080`
- **THEN** a resposta é 403 e nenhuma análise é feita

### Requirement: Rota POST /api/analisar
`POST /api/analisar` com corpo `{"texto": string, "explicar": boolean opcional}` SHALL responder 200 com o mesmo objeto de resultado da API Python, incluindo `tokens` quando `explicar` for verdadeiro, e o campo adicional `latencia_ms` com o tempo de processamento no servidor.

#### Scenario: Análise com explicação
- **WHEN** o cliente envia `{"texto": "nao gostei do atendimento", "explicar": true}`
- **THEN** a resposta é 200 com `label` `negativo`, `tokens` contendo `NEG_gostei` e `latencia_ms` numérico

#### Scenario: Sem explicação
- **WHEN** o cliente envia `{"texto": "adorei"}`
- **THEN** a resposta é 200, com `label` `positivo` e sem o campo `tokens`

### Requirement: Rota POST /api/lote
`POST /api/lote` com corpo `{"textos": [string, ...], "explicar": boolean opcional}` SHALL responder 200 com `{"resultados": [...]}`, na mesma ordem e com o mesmo tamanho da entrada. Listas com mais de 10.000 itens SHALL ser rejeitadas com 413.

#### Scenario: Lote pequeno
- **WHEN** o cliente envia `{"textos": ["adorei", "pessimo", ""]}`
- **THEN** a resposta tem 3 resultados, iguais um a um aos da análise individual

#### Scenario: Lote acima do limite
- **WHEN** o cliente envia uma lista de 10.001 textos
- **THEN** a resposta é 413 com mensagem de erro, e nada é analisado

### Requirement: Rota GET /api/saude
`GET /api/saude` SHALL responder 200 com `versao`, `modo` e `latencia_p95_ms`, sendo este o p95 do tempo de processamento das últimas 1.000 análises (ou `null` se ainda não houve análise).

#### Scenario: Antes de qualquer análise
- **WHEN** o servidor acabou de subir e o cliente consulta `/api/saude`
- **THEN** a resposta tem `modo` `lexico`, a `versao` dos artefatos e `latencia_p95_ms` `null`

#### Scenario: Depois de análises
- **WHEN** foram feitas 10 análises e o cliente consulta `/api/saude`
- **THEN** `latencia_p95_ms` é um número maior que 0

### Requirement: Rota GET /
`GET /` SHALL responder 200 com a página HTML da interface, e os arquivos estáticos referenciados por ela SHALL ser servidos pelo próprio servidor a partir do pacote instalado.

#### Scenario: Página inicial
- **WHEN** o navegador abre `http://127.0.0.1:8080/`
- **THEN** a resposta é 200 com `Content-Type: text/html; charset=utf-8`

### Requirement: Erros da API em JSON
Erros SHALL ser respondidos em JSON no formato `{"erro": mensagem}`: 400 para JSON inválido ou campos com tipo errado, 404 para rota desconhecida, 405 para método não suportado, 413 para corpo acima de 16 MB ou lote acima do limite e 415 para `Content-Type` diferente de `application/json` nas rotas POST.

#### Scenario: JSON inválido
- **WHEN** o cliente envia `nao e json` para `/api/analisar`
- **THEN** a resposta é 400 com o campo `erro`

#### Scenario: Campo com tipo errado
- **WHEN** o cliente envia `{"texto": 42}` para `/api/analisar`
- **THEN** a resposta é 400 com o campo `erro`

#### Scenario: Content-Type de formulário
- **WHEN** um site externo faz um POST de formulário (`text/plain` ou `application/x-www-form-urlencoded`) para `/api/analisar`
- **THEN** a resposta é 415 e nenhuma análise é feita

#### Scenario: Rota desconhecida
- **WHEN** o cliente pede `GET /api/nada`
- **THEN** a resposta é 404 com o campo `erro`

### Requirement: Privacidade dos textos
O servidor SHALL NOT gravar textos recebidos em disco nem em log, e SHALL NOT fazer chamadas de rede de saída. O log no terminal SHALL conter apenas método, rota, status e duração.

#### Scenario: Log de requisição
- **WHEN** o cliente analisa o texto "segredo123"
- **THEN** o log do servidor registra `POST /api/analisar 200` e a duração, sem conter "segredo123"

### Requirement: Cabeçalhos de segurança
Todas as respostas SHALL incluir `X-Content-Type-Options: nosniff` e `Content-Security-Policy` que permita recursos apenas da própria origem, e as respostas da API SHALL incluir `Cache-Control: no-store`. O servidor SHALL NOT enviar cabeçalhos CORS.

#### Scenario: Cabeçalhos na página
- **WHEN** o navegador abre `/`
- **THEN** a resposta inclui `Content-Security-Policy` com `default-src 'self'` e `X-Content-Type-Options: nosniff`

#### Scenario: Sem CORS
- **WHEN** um cliente envia `OPTIONS /api/analisar` com `Origin: https://outro.site`
- **THEN** a resposta não contém `Access-Control-Allow-Origin`

### Requirement: Latência de ida e volta
Para textos de até 280 caracteres, a ida e volta de `POST /api/analisar` medida no cliente na mesma máquina SHALL ter p95 de até 50 ms.

#### Scenario: Medição de ida e volta
- **WHEN** um cliente local faz 500 requisições sequenciais de textos curtos
- **THEN** o p95 do tempo de ida e volta é de até 50 ms

### Requirement: Requisições concorrentes
O servidor SHALL atender requisições concorrentes sem misturar respostas, de modo que cada cliente receba o resultado do próprio texto.

#### Scenario: Duas abas ao mesmo tempo
- **WHEN** 8 clientes enviam textos diferentes em paralelo
- **THEN** cada resposta corresponde ao texto enviado pelo seu cliente
