# classificacao-sentimento Specification

## Purpose

Classificar textos curtos em português como positivo, negativo ou neutro, com score contínuo, confiança e explicação opcional, rodando localmente, de forma determinística e com baixa latência.

## Requirements

### Requirement: Estrutura do resultado
Cada análise SHALL devolver um objeto com `label` (`positivo`, `negativo` ou `neutro`), `score` (número de −1 a +1), `confianca` (número de 0 a 1), `versao` (versão dos artefatos), `modo` (`lexico` nesta versão) e `truncado` (booleano).

#### Scenario: Análise de texto positivo
- **WHEN** o texto "o produto chegou rapido, adorei!" é analisado
- **THEN** o resultado tem `label` igual a `positivo`, `score` maior que 0, `confianca` entre 0 e 1, `modo` igual a `lexico` e `truncado` falso

### Requirement: Score léxico com negação, intensidade e contraste
O score SHALL somar as polaridades do léxico dos tokens, invertendo e atenuando (fator −0,8) termos negados, multiplicando o termo seguinte a um intensificador por 1,5 e a um atenuador por 0,5, e pesando 1,5 os termos após o último conectivo de contraste e 0,5 os anteriores. O total SHALL ser normalizado para [−1, 1] pelo tamanho do texto.

#### Scenario: Negação inverte a polaridade
- **WHEN** os textos "gostei" e "nao gostei" são analisados
- **THEN** o primeiro tem `score` positivo e o segundo, `score` negativo

#### Scenario: Intensificador amplia o score
- **WHEN** os textos "bom" e "muito bom" são analisados
- **THEN** o `score` de "muito bom" é maior que o de "bom"

#### Scenario: Contraste privilegia a segunda oração
- **WHEN** o texto "o produto e bom, mas a entrega foi pessima" é analisado
- **THEN** o `label` é `negativo`

#### Scenario: Riso e emojis contam como polaridade
- **WHEN** o texto "chegou hoje kkkk 😍" é analisado
- **THEN** o `score` é positivo

### Requirement: Decisão do rótulo por limiar
O rótulo SHALL ser `positivo` quando o score for maior que 0,15, `negativo` quando for menor que −0,15 e `neutro` nos demais casos; o rótulo e o sinal do score SHALL nunca se contradizer.

#### Scenario: Texto sem termos de sentimento
- **WHEN** o texto "o pedido chegou na terca" é analisado
- **THEN** o `label` é `neutro` e o `score` está entre −0,15 e 0,15

### Requirement: Cálculo da confiança
Para `positivo` e `negativo`, a `confianca` SHALL ser o valor absoluto do score. Para `neutro`, SHALL ser 1 − |score| / 0,15. Texto sem tokens SHALL resultar em `neutro`, `score` 0 e `confianca` 0.

#### Scenario: Texto vazio
- **WHEN** o texto "" é analisado
- **THEN** o resultado é `label` `neutro`, `score` 0 e `confianca` 0

#### Scenario: Neutro sem polaridade
- **WHEN** um texto com tokens, mas sem nenhum termo do léxico, é analisado
- **THEN** o resultado é `neutro` com `confianca` 1

### Requirement: Limite de tamanho da entrada
Textos com mais de 5.000 caracteres SHALL ser truncados nos primeiros 5.000 antes da análise, e o resultado SHALL indicar `truncado` verdadeiro.

#### Scenario: Texto longo
- **WHEN** um texto de 6.000 caracteres é analisado
- **THEN** o resultado tem `truncado` verdadeiro e é igual ao da análise dos seus primeiros 5.000 caracteres, exceto pelo campo `truncado`

### Requirement: Rejeição de entrada que não é texto
A análise SHALL rejeitar com erro de tipo qualquer entrada que não seja uma string, sem devolver resultado parcial.

#### Scenario: Entrada numérica
- **WHEN** o valor 42 é passado para análise
- **THEN** a chamada falha com erro de tipo

### Requirement: Explicação opcional
Quando a explicação for solicitada, o resultado SHALL incluir `tokens`: até 5 itens `{token, peso}` com os tokens de maior contribuição absoluta ao score, ordenados de forma decrescente pelo valor absoluto, com `peso` positivo ou negativo. Sem solicitação, `tokens` SHALL estar ausente.

#### Scenario: Explicação de texto negado
- **WHEN** o texto "nao gostei do atendimento" é analisado com explicação
- **THEN** `tokens` contém `NEG_gostei` com `peso` negativo

#### Scenario: Explicação não solicitada
- **WHEN** um texto é analisado sem pedir explicação
- **THEN** o resultado não contém o campo `tokens`

### Requirement: Análise em lote
A análise em lote SHALL receber uma lista de textos e devolver uma lista de resultados do mesmo tamanho e na mesma ordem, cada um idêntico ao da análise individual do texto correspondente.

#### Scenario: Lote equivale a análises individuais
- **WHEN** a lista ["adorei", "pessimo", ""] é analisada em lote
- **THEN** são devolvidos 3 resultados, iguais um a um aos das análises individuais

#### Scenario: Lote vazio
- **WHEN** uma lista vazia é analisada em lote
- **THEN** é devolvida uma lista vazia

### Requirement: Carregamento de artefatos
O analisador SHALL carregar léxico, tabela de emojis e configuração de um diretório informado, ou dos artefatos padrão embutidos quando nenhum diretório for informado. Um diretório inexistente ou sem artefato obrigatório SHALL gerar erro claro, que nomeie o arquivo faltante.

#### Scenario: Artefatos padrão
- **WHEN** o analisador é carregado sem diretório
- **THEN** ele usa os artefatos embutidos e o `versao` do resultado é o do `config.json` embutido

#### Scenario: Diretório sem léxico
- **WHEN** o analisador é carregado de um diretório sem `lexico.tsv`
- **THEN** o carregamento falha com uma mensagem que menciona `lexico.tsv`

### Requirement: Determinismo da classificação
A mesma entrada, com os mesmos artefatos, SHALL produzir sempre o mesmo resultado, em qualquer processo, execução ou sistema operacional suportado.

#### Scenario: Processos diferentes
- **WHEN** o mesmo texto é analisado em dois processos Python diferentes
- **THEN** os resultados são idênticos campo a campo

### Requirement: Operação offline
A análise e o carregamento de artefatos SHALL NOT fazer nenhuma chamada de rede nem gravar o texto analisado em disco.

#### Scenario: Sem rede
- **WHEN** um texto é analisado numa máquina sem conexão de rede
- **THEN** a análise conclui normalmente

### Requirement: Latência por texto
A análise individual de textos de até 280 caracteres SHALL ter latência p95 de até 1 ms numa única thread, medida em pelo menos 10.000 textos após o carregamento dos artefatos.

#### Scenario: Benchmark de latência
- **WHEN** o benchmark analisa 10.000 textos de até 280 caracteres na máquina-alvo
- **THEN** o p95 relatado é de até 1 ms e o relatório inclui p50, p95, p99 e textos por segundo

### Requirement: Uso de memória
O processo com o analisador carregado SHALL usar no máximo 100 MB de RAM, e os artefatos SHALL ocupar no máximo 20 MB em disco.

#### Scenario: Memória após carregamento
- **WHEN** o analisador é carregado e analisa 10.000 textos
- **THEN** o pico de memória residente do processo fica em até 100 MB
