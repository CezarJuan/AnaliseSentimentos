# Spec Delta

## Purpose

Transformar texto bruto em português do Brasil informal numa sequência determinística de tokens normalizados e anotados, usada tanto pela classificação quanto pelo treino futuro do modelo.

## ADDED Requirements

### Requirement: Normalização de caixa, Unicode e acentos
O sistema SHALL aplicar normalização Unicode NFKC, converter para minúsculas e remover acentos, de modo que formas com e sem acento produzam os mesmos tokens.

#### Scenario: Texto com e sem acento
- **WHEN** os textos "Péssimo, NÃO gostei" e "pessimo, nao gostei" são pré-processados
- **THEN** as duas sequências de tokens são idênticas

### Requirement: Substituição de URLs, menções e números
O sistema SHALL substituir URLs pelo token `<url>`, menções iniciadas por `@` pelo token `<user>` e sequências numéricas pelo token `<num>`.

#### Scenario: Texto com URL, menção e número
- **WHEN** o texto "@loja comprei 2 em https://ex.com/p" é pré-processado
- **THEN** os tokens são `<user>`, `comprei`, `<num>`, `em`, `<url>`

### Requirement: Mapeamento de emojis e emoticons
O sistema SHALL mapear emojis e emoticons presentes na tabela de emojis para `<emo_pos>` ou `<emo_neg>`, reconhecendo emoticons independentemente de maiúsculas/minúsculas (por exemplo `:D` e `:d`, `XD` e `xd`).

#### Scenario: Emoji positivo
- **WHEN** o texto "amei 😍" é pré-processado
- **THEN** os tokens são `amei`, `<emo_pos>`

#### Scenario: Emoticon com letra maiúscula
- **WHEN** o texto "chegou rapido :D" é pré-processado
- **THEN** a sequência termina em `<emo_pos>`

### Requirement: Reconhecimento de risadas
O sistema SHALL reconhecer risadas em PT-BR (sequências como `kkk`, `rsrs`, `haha`, `hehe`, com qualquer comprimento a partir de 3 caracteres) e substituí-las pelo token `<riso>` antes da redução de alongamentos.

#### Scenario: Risada longa
- **WHEN** o texto "kkkkkkk muito bom" é pré-processado
- **THEN** o primeiro token é `<riso>`

### Requirement: Redução de alongamentos
O sistema SHALL reduzir uma letra repetida 3 ou mais vezes seguidas a uma única ocorrência e SHALL indicar que o texto continha alongamento.

#### Scenario: Palavra alongada
- **WHEN** o texto "muuuuito bom" é pré-processado
- **THEN** os tokens são `muito`, `bom` e o resultado indica alongamento

#### Scenario: Letra dupla legítima
- **WHEN** o texto "carro" é pré-processado
- **THEN** o token é `carro`, sem alongamento indicado

### Requirement: Expansão de abreviações
O sistema SHALL expandir abreviações de um dicionário fixo, incluindo `vc`→`voce`, `n`→`nao`, `mt`/`mto`→`muito`, `tb`→`tambem` e `nd`→`nada`, apenas quando a abreviação for um token inteiro.

#### Scenario: Abreviações comuns
- **WHEN** o texto "vc n vai gostar mt" é pré-processado
- **THEN** os tokens são `voce`, `nao`, `NEG_vai`, `NEG_gostar`, `muito`

### Requirement: Fronteiras de pontuação
O sistema SHALL emitir um token de fronteira `<pont>` para pontuação de fim de oração (`.`, `,`, `;`, `:`), o token `<excl>` para uma ou mais `!` e o token `<interr>` para uma ou mais `?`; os demais símbolos SHALL ser descartados.

#### Scenario: Exclamações repetidas
- **WHEN** o texto "adorei!!!" é pré-processado
- **THEN** os tokens são `adorei`, `<excl>`

#### Scenario: Vírgula vira fronteira
- **WHEN** o texto "ruim, caro" é pré-processado
- **THEN** os tokens são `ruim`, `<pont>`, `caro`

### Requirement: Escopo de negação
Após um negador (`nao`, `nunca`, `nem`, `jamais`, `nada`, `ninguem`), o sistema SHALL prefixar com `NEG_` até 3 tokens seguintes, parando antes de um token de fronteira, de outro negador ou de um conectivo de contraste. Placeholders, intensificadores e atenuadores SHALL NOT receber o prefixo, mas contam no limite de 3.

#### Scenario: Negação simples
- **WHEN** o texto "nao gostei" é pré-processado
- **THEN** os tokens são `nao`, `NEG_gostei`

#### Scenario: Negação termina na pontuação
- **WHEN** o texto "nao gostei, mas o preco e bom" é pré-processado
- **THEN** só `gostei` recebe o prefixo `NEG_` e `mas` permanece sem prefixo

#### Scenario: Intensificador dentro do escopo
- **WHEN** o texto "nao e muito bom" é pré-processado
- **THEN** os tokens são `nao`, `NEG_e`, `muito`, `NEG_bom`

#### Scenario: Limite de 3 tokens
- **WHEN** o texto "nao achei o produto bom" é pré-processado
- **THEN** `achei`, `o` e `produto` recebem `NEG_` e `bom` não recebe

### Requirement: Entrada vazia ou sem tokens
O sistema SHALL devolver uma sequência vazia de tokens para texto vazio ou composto só de espaços e símbolos descartados, sem gerar erro.

#### Scenario: Texto vazio
- **WHEN** o texto "   " é pré-processado
- **THEN** a sequência de tokens é vazia

### Requirement: Determinismo do pré-processamento
O sistema SHALL produzir exatamente a mesma sequência de tokens para a mesma entrada, independentemente de processo, execução, sistema operacional ou ordem das chamadas.

#### Scenario: Execuções repetidas
- **WHEN** o mesmo texto é pré-processado em dois processos Python diferentes
- **THEN** as duas sequências de tokens são idênticas
