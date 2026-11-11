# Spec Delta

## Purpose

Oferecer uma página web local para experimentar o analisador: análise ao vivo enquanto se digita, explicação visual da decisão, processamento de arquivos em lote e histórico da sessão, funcionando totalmente offline e acessível por teclado.

## ADDED Requirements

### Requirement: Análise ao vivo
A página SHALL analisar o texto do campo principal 150 ms depois da última digitação, e Ctrl+Enter (ou Cmd+Enter) SHALL forçar a análise imediata. Um campo vazio SHALL limpar o resultado sem enviar requisição.

#### Scenario: Digitação contínua
- **WHEN** o usuário digita "adorei" sem pausas maiores que 150 ms
- **THEN** só é enviada uma requisição, 150 ms após a última tecla, e o resultado mostra positivo

#### Scenario: Forçar análise
- **WHEN** o usuário digita um texto e pressiona Ctrl+Enter antes de 150 ms
- **THEN** a análise é enviada imediatamente

#### Scenario: Campo apagado
- **WHEN** o usuário apaga todo o texto
- **THEN** a área de resultado volta ao estado inicial

### Requirement: Descarte de resultados desatualizados
Quando o texto muda enquanto uma análise está em andamento, a página SHALL cancelar a requisição anterior e SHALL nunca exibir o resultado de um texto que já não está no campo.

#### Scenario: Resposta lenta de texto antigo
- **WHEN** a análise de "bom" ainda não respondeu e o usuário altera o texto para "bom nao"
- **THEN** a requisição de "bom" é cancelada e só o resultado de "bom nao" aparece

### Requirement: Apresentação do resultado
O resultado SHALL mostrar o rótulo em texto, acompanhado de ícone e cor próprios de positivo, negativo e neutro, a confiança em porcentagem, a latência de ida e volta em ms e uma barra de −1 a +1 com marcador na posição do score. A cor SHALL nunca ser o único indicador do rótulo.

#### Scenario: Resultado negativo
- **WHEN** o texto "pessimo, veio quebrado" é analisado
- **THEN** a página mostra o texto "Negativo" com ícone e cor de negativo, a confiança como porcentagem, a latência em ms e o marcador da barra à esquerda do centro

#### Scenario: Leitor de tela
- **WHEN** um resultado novo é exibido
- **THEN** o rótulo e a confiança são anunciados por uma região `aria-live` educada, e a barra expõe o score como valor acessível

### Requirement: Destaque de tokens
A página SHALL pedir a explicação e SHALL exibir os tokens de maior peso como uma lista com sinal (verde e "+" para positivo, vermelho e "−" para negativo) e marca visível de "negado" nos tokens com `NEG_`. As palavras do texto original que correspondem a esses tokens SHALL aparecer sublinhadas com a mesma cor e sinal.

#### Scenario: Texto com negação
- **WHEN** o texto "nao gostei do atendimento" é analisado
- **THEN** a lista mostra "gostei" com sinal negativo e a marca "negado", e a palavra "gostei" do texto aparece sublinhada como negativa

#### Scenario: Texto com acento e alongamento
- **WHEN** o texto "Ótimooo produto" é analisado
- **THEN** a palavra "Ótimooo" do texto aparece sublinhada como positiva

#### Scenario: Token sem palavra correspondente
- **WHEN** o texto "chegou 😍" é analisado
- **THEN** a lista mostra o token do emoji com sinal positivo, mesmo sem palavra sublinhada no texto

### Requirement: Modo lote por arquivo
A página SHALL aceitar upload de `.txt` (um texto por linha, linhas em branco ignoradas) ou `.csv` (coluna `texto` se houver cabeçalho com esse nome, senão a primeira coluna), SHALL exibir uma tabela com texto, rótulo, score e confiança e SHALL oferecer o download dos resultados em CSV UTF-8. Arquivos com mais de 10.000 textos SHALL ser enviados em partes de até 10.000.

#### Scenario: Arquivo .txt
- **WHEN** o usuário envia um `.txt` com 3 linhas de texto e uma linha em branco
- **THEN** a tabela mostra 3 linhas de resultado, na ordem do arquivo

#### Scenario: CSV com cabeçalho
- **WHEN** o usuário envia um CSV com cabeçalho `id,texto,data`, com campos entre aspas contendo vírgulas e quebras de linha
- **THEN** são analisados os valores da coluna `texto`, inteiros

#### Scenario: Download do resultado
- **WHEN** o usuário clica em baixar CSV após um lote
- **THEN** é baixado um arquivo com cabeçalho `texto,label,score,confianca`, com os campos escapados corretamente

#### Scenario: Arquivo grande
- **WHEN** o usuário envia um `.txt` com 25.000 linhas
- **THEN** a página faz 3 requisições de lote e a tabela mostra os 25.000 resultados na ordem original

#### Scenario: Tipo de arquivo não suportado
- **WHEN** o usuário envia um arquivo `.pdf`
- **THEN** a página mostra uma mensagem de erro e não envia nada ao servidor

### Requirement: Histórico da sessão
A página SHALL guardar, só em memória, as últimas 20 análises confirmadas (por Ctrl+Enter ou pelo botão Analisar), mostrando texto, rótulo e score, e SHALL oferecer um botão para limpar. As análises disparadas pela digitação ao vivo SHALL NOT entrar no histórico.

#### Scenario: Limite de 20
- **WHEN** o usuário confirma 21 análises
- **THEN** o histórico mostra as 20 mais recentes, a mais nova primeiro

#### Scenario: Recarregar a página
- **WHEN** o usuário recarrega a página
- **THEN** o histórico está vazio

### Requirement: Rodapé de status
O rodapé SHALL mostrar a versão dos artefatos e o modo de operação ("léxico (fallback)" ou "modelo carregado"), obtidos de `/api/saude`, e SHALL indicar quando o servidor não responde.

#### Scenario: Servidor no ar
- **WHEN** a página carrega com o servidor rodando no modo léxico
- **THEN** o rodapé mostra a versão e "léxico (fallback)"

#### Scenario: Servidor fora do ar
- **WHEN** o servidor é encerrado e o usuário tenta analisar
- **THEN** a página mostra uma mensagem de que o servidor não está respondendo, sem travar

### Requirement: Acessibilidade e temas
A página SHALL ser operável só pelo teclado, com foco visível em todos os controles, SHALL ter contraste de cor nível AA (4,5:1 para texto) nos temas claro e escuro, SHALL seguir o tema do sistema por padrão e SHALL oferecer um botão para alternar o tema.

#### Scenario: Navegação por teclado
- **WHEN** o usuário percorre a página com Tab
- **THEN** campo de texto, botão Analisar, upload, download, limpar histórico e alternância de tema recebem foco visível, nessa ordem lógica

#### Scenario: Tema escuro do sistema
- **WHEN** o sistema está em modo escuro e a página é aberta
- **THEN** a página usa o tema escuro

### Requirement: Funcionamento offline e tamanho
A página SHALL funcionar sem acesso à internet, sem carregar nenhum recurso externo (fontes, scripts, estilos ou imagens), e o total de HTML, CSS e JavaScript SHALL ser de até 100 KB.

#### Scenario: Sem internet
- **WHEN** a máquina está offline e o usuário abre a página
- **THEN** todas as funções operam normalmente

#### Scenario: Tamanho dos estáticos
- **WHEN** os arquivos estáticos do pacote são somados
- **THEN** o total é de até 100 KB

### Requirement: Privacidade na página
A página SHALL NOT gravar textos analisados em armazenamento do navegador (localStorage, sessionStorage, IndexedDB ou cookies). Só a preferência de tema MAY ser lembrada.

#### Scenario: Armazenamento após uso
- **WHEN** o usuário analisa textos e processa um lote
- **THEN** o armazenamento do navegador da origem contém no máximo a preferência de tema
