# cli-sentimento Specification

## Purpose

Permitir analisar sentimento pela linha de comando, tanto um texto avulso quanto um fluxo JSONL pela entrada padrão, para uso manual e em pipelines de shell.

## Requirements

### Requirement: Análise de texto avulso
O comando `sentimento "<texto>"` SHALL imprimir na saída padrão uma única linha JSON com o resultado da análise e terminar com código de saída 0.

#### Scenario: Texto como argumento
- **WHEN** o usuário executa `sentimento "adorei o produto"`
- **THEN** a saída é uma linha JSON com `label` `positivo` e o código de saída é 0

### Requirement: Fluxo JSONL pela entrada padrão
Sem texto como argumento, o comando SHALL ler a entrada padrão em JSONL, onde cada linha é um objeto com o campo `texto` e, opcionalmente, `id`. Para cada linha, SHALL escrever na saída padrão uma linha JSON com o resultado, na mesma ordem e repetindo o `id` quando presente. Linhas em branco SHALL ser ignoradas.

#### Scenario: Duas linhas com id
- **WHEN** a entrada padrão contém `{"id": 1, "texto": "adorei"}` e `{"id": 2, "texto": "pessimo"}`
- **THEN** a saída tem duas linhas JSON, com `id` 1 e `positivo` e depois `id` 2 e `negativo`

### Requirement: Linhas inválidas no fluxo
Uma linha que não seja JSON válido, ou não tenha `texto` do tipo string, SHALL gerar na saída padrão uma linha JSON com o campo `erro` e o número da linha, sem interromper as demais. Ao final, o código de saída SHALL ser 1 se houve alguma linha inválida, ou 0 se não houve.

#### Scenario: Linha malformada no meio
- **WHEN** a entrada padrão contém uma linha válida, uma linha `nao e json` e outra linha válida
- **THEN** a saída tem três linhas, a segunda com `erro` e `linha` 2, e o código de saída é 1

### Requirement: Opções da CLI
A CLI SHALL aceitar `--explicar` para incluir os tokens de maior peso, `--modelo <dir>` para carregar artefatos de um diretório e `--versao` para imprimir a versão dos artefatos e sair. Um diretório de artefatos inválido SHALL gerar uma mensagem de erro na saída de erro e código de saída 2.

#### Scenario: Explicação pela CLI
- **WHEN** o usuário executa `sentimento --explicar "nao gostei"`
- **THEN** a linha JSON inclui o campo `tokens`

#### Scenario: Diretório de modelo inexistente
- **WHEN** o usuário executa `sentimento --modelo pasta_inexistente "oi"`
- **THEN** uma mensagem de erro vai para a saída de erro e o código de saída é 2

### Requirement: Codificação UTF-8
A CLI SHALL ler e escrever em UTF-8 em todos os sistemas suportados, incluindo Windows, e SHALL preservar caracteres não ASCII na saída JSON sem escapá-los.

#### Scenario: Acentos e emojis no Windows
- **WHEN** a CLI processa no Windows o texto "ótimo 😍" vindo da entrada padrão
- **THEN** a análise vê o texto corretamente e a saída JSON é UTF-8 válido
