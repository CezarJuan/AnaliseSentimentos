# Roteiro manual: interface web

Verificação no navegador do que os testes automáticos não cobrem: comportamento visual, teclado, temas e modo offline. Rode em **Chrome ou Edge** e em **Firefox**.

Para preparar:

```powershell
.\.venv\Scripts\Activate.ps1
sentimento serve
```

Abra `http://127.0.0.1:8080/` e as ferramentas do desenvolvedor (F12), aba **Rede**.

Para cada passo, marque `[x]` quando passar ou anote o problema. Registre o navegador e a data no fim.

## A. Análise ao vivo (tarefa 4.2)

- [ ] A1. Digite `adorei` sem pausas. Na aba Rede, aparece **uma** requisição `analisar`, ~150 ms após a última tecla. O resultado mostra **▲ Positivo**.
- [ ] A2. Digite `bom` e pressione **Ctrl+Enter** logo em seguida. A análise sai na hora, e o texto entra no Histórico.
- [ ] A3. Apague todo o texto. O resultado volta para "Digite um texto para ver o sentimento.", e nenhuma requisição nova aparece.
- [ ] A4. Na aba Rede, ative a limitação "3G lento". Digite `bom`, espere ~200 ms e acrescente ` nao`. A primeira requisição aparece como **cancelada**, e só o resultado de `bom nao` é exibido. Desative a limitação.

## B. Apresentação do resultado (tarefa 4.2)

- [ ] B1. Digite `pessimo, veio quebrado`. Aparecem o texto **Negativo**, o ícone ▼ e a cor vermelha, a confiança em %, a latência em ms e o marcador da barra à esquerda do centro.
- [ ] B2. Com um leitor de tela (Narrador: Win+Ctrl+Enter; ou NVDA), um resultado novo é anunciado como "Negativo, confiança NN%". A barra é lida com o valor do score.

## C. Destaque de tokens (tarefa 4.2)

- [ ] C1. `nao gostei do atendimento`: a lista mostra **−0,56 gostei NEGADO**. No texto, "gostei" aparece sublinhado em vermelho, ondulado, com `−¬`.
- [ ] C2. `Ótimooo produto`: "Ótimooo" aparece sublinhado em verde, com `+`.
- [ ] C3. `chegou 😍`: a lista mostra **+0,80 emoji positivo**, e nenhuma palavra fica sublinhada.

## D. Modo lote (tarefa 4.3)

- [ ] D1. Envie `tests/dados/lote_exemplo.csv`. A tabela mostra 5 linhas, e a linha 5 traz o texto inteiro, com a quebra de linha e as aspas.
- [ ] D2. Clique em **Baixar CSV**. O arquivo `lote_exemplo-sentimentos.csv` tem o cabeçalho `texto,label,score,confianca`. Ao abrir no Excel, os acentos aparecem certos, a linha 4 mostra `'=1+1 ...` como texto (não calcula 2) e a linha 5 continua uma célula só.
- [ ] D3. Gere um `.txt` grande no PowerShell e envie:
  `1..25000 | ForEach-Object { "texto $_ muito bom" } | Set-Content -Encoding utf8 grande.txt`
  O status mostra "parte 1 de 3…" e, no fim, "25.000 textos analisados… Mostrando 1.000 de 25.000". O CSV baixado tem 25.001 linhas.
- [ ] D4. Envie um `.pdf` qualquer. Aparece a mensagem "tipo não suportado", e nenhuma requisição `lote` é feita.

## E. Histórico e rodapé (tarefa 4.3)

- [ ] E1. Confirme 21 análises com Ctrl+Enter (textos diferentes). O histórico mostra 20, a mais nova primeiro. Clicar num item recoloca o texto no campo.
- [ ] E2. **Limpar histórico** esvazia a lista. Recarregar a página (F5) também deixa o histórico vazio.
- [ ] E3. O rodapé mostra "Versão 0.1.0 · léxico (fallback)".
- [ ] E4. Encerre o servidor (Ctrl+C no terminal) e tente analisar. Aparece a mensagem "O servidor não está respondendo…", a página não trava e o rodapé muda para o mesmo aviso. Suba o servidor de novo: em até 10 s, o rodapé volta ao normal.

## F. Teclado, temas e contraste (tarefa 5.2)

- [ ] F1. Recarregue e percorra com **Tab**. O foco aparece visível, nesta ordem: campo de texto → Analisar → Escolher arquivo → Baixar CSV (pulado enquanto desabilitado) → Limpar histórico → (itens do histórico) → tema.
- [ ] F2. "Escolher arquivo" abre o seletor com **Enter** ou **Espaço**.
- [ ] F3. Com o Windows em modo escuro (Configurações → Personalização → Cores), a página abre no tema escuro. Com o Windows claro, abre no tema claro.
- [ ] F4. O botão de tema alterna claro e escuro, e a escolha permanece após recarregar.
- [ ] F5. Nos dois temas, todo texto está legível. Opcional: rode o Lighthouse → Acessibilidade, sem erros de contraste.

## G. Offline e privacidade (tarefa 5.2)

- [ ] G1. Desligue o Wi-Fi ou cabo e recarregue. A página carrega e analisa normalmente. Na aba Rede, só aparecem requisições para `127.0.0.1`.
- [ ] G2. Depois de analisar textos e um lote, abra **Aplicativo → Armazenamento**. Local Storage contém no máximo `sentimento-tema`. Session Storage, IndexedDB e Cookies estão vazios.
- [ ] G3. No terminal do servidor, as linhas de log mostram só método, rota, status e ms, sem nenhum texto digitado.

## Registro

| Navegador e versão | Data | Resultado | Observações |
| --- | --- | --- | --- |
| Chrome (versão não registrada) | 2026-11-10 | Passou | Relato do usuário: "funcionou bem"; os passos não foram marcados um a um |
| Firefox | | Pendente | |
