# Design

## Context

O projeto ainda não tem código; a única referência é o documento `Spec Análise de Sentimentos Local de Baixa Latência.md` na raiz. A motivação está em proposal.md, e os comportamentos exigidos estão nas specs de `preprocessamento-texto`, `classificacao-sentimento` e `cli-sentimento`. Este design cobre como construir o núcleo léxico de forma que a change seguinte (modelo treinado) se encaixe sem refazer o pré-processamento.

Restrições que moldam o design: Python 3.10+, Linux/macOS/Windows em x86-64 e ARM64, p95 ≤ 1 ms por texto, e nenhuma dependência pesada em tempo de execução.

## Goals / Non-Goals

**Goals:**
- Pré-processamento como função pura e isolada, que o treino futuro importa sem mudança.
- Estrutura de pacote e de artefatos que já prevê `W.npy`/`b.npy` sem exigir esses arquivos.
- Benchmark reproduzível desde o primeiro dia.

**Non-Goals:**
- Atingir macro-F1 ≥ 0,75: isso só é medido com o modelo treinado. Aqui o léxico só precisa acertar os casos claros.
- Vetorização com NumPy no lote: sem matriz de pesos, não há o que vetorizar.
- Integração com CI: o repositório não tem CI. O benchmark fica como script e teste marcado, para ser ligado depois.

## Decisions

### D1. Layout do pacote

```
sentimento/
  __init__.py          # exporta Analisador, __version__
  preprocessamento.py  # preprocessar(texto) -> Preprocessado(tokens, alongado)
  lexico.py            # carga de lexico/emojis, features_lexicas(tokens)
  analisador.py        # Analisador.carregar(), analisar(), analisar_lote()
  cli.py               # main(argv) ; registrado como script "sentimento"
  __main__.py          # python -m sentimento
  recursos/            # artefatos padrão: lexico.tsv, emojis.tsv, config.json
tests/
bench/benchmark.py
pyproject.toml
```

O pré-processamento não conhece o léxico de polaridade: recebe só as tabelas de que precisa (emojis, abreviações, negadores, intensificadores, conectivos). Assim o treino pode reutilizá-lo sem carregar o léxico. Os artefatos padrão são lidos com `importlib.resources`, que funciona tanto instalado quanto em modo editável.

Alternativa descartada: um módulo único. Ficaria mais simples agora, mas mistura o contrato compartilhado com o treino (pré-processamento) e as partes que vão mudar (decisão por léxico, que vira modelo).

### D2. Ordem do pipeline (corrige a spec original)

```
 bruto
  |  truncar em 5000 (marca truncado)
  v
 [a] url -> <url>, @x -> <user>               (antes dos emoticons: ":/" casaria em "https://")
 [b] emoticons ASCII -> <emo_pos>/<emo_neg>   (antes do lower: ":D", "XD"; exige borda de espaco/inicio/fim)
 [c] NFKC + lower + remove acentos (NFD, descarta categoria Mn)
 [d] emojis Unicode -> <emo_*> ; digitos -> <num>   (a remoção de Mn tira o VS16, o que ajuda a casar)
 [e] risadas -> <riso>                        (antes do alongamento, senão "kkkk" -> "k")
 [f] alongamento 3+ -> 1 (marca alongado)
 [g] tokenizar: <\w+> | \w+ | [.,;:] -> <pont> | !+ -> <excl> | ?+ -> <interr>
 [h] abreviacoes (por token inteiro)
 [i] escopo NEG_ (para em <pont>/<excl>/<interr>, negador, conectivo; max 3)
  v
 tokens
```

As diferenças em relação ao documento original são decisões tomadas nesta change:
- **Emoticons antes do lower**: senão a tabela teria que listar `:d` e `xd`. A tabela é casada sem diferenciar caixa e contra o texto original.
- **URLs e menções primeiro**: sem isso, emoticons como `:/` e `:p` casariam dentro de URLs. A regex de URL não diferencia caixa, então não depende do lower.
- **Placeholders nos emoticons**: na etapa [b], o emoticon é trocado pelo placeholder já com espaços em volta, para não colar em palavras.
- **Abreviações depois da tokenização**: o dicionário só vale para tokens inteiros (`n` sozinho vira `nao`; o `n` dentro de `nunca` não). Fazer isso com regex de borda de palavra antes de tokenizar dá o mesmo resultado, só que mais caro.
- **Fronteira `<pont>`**: o documento original mandava a negação parar na pontuação, mas a regex descartava a pontuação. Agora a pontuação vira token. Isso também significa que `<pont>` entra nos bigramas do modelo futuro, o que é aceitável e até informativo.
- **Intensificadores e placeholders imunes ao `NEG_`**: senão `nao e muito bom` perderia o 1,5. Eles contam no limite de 3 tokens, o que preserva a ideia do "escopo curto".

Todas as regex são compiladas na importação do módulo.

### D3. Score léxico e decisão

```
 para cada token t, na posicao i:
   se t e intensificador/atenuador: peso_prox = 1.5 | 0.5 ; continue
   neg = t comeca com "NEG_" ; base = t sem prefixo
   v = LEXICO.get(base, 0)
   se neg: v = -0.8 * v
   c = 1.5 se i > ultimo_contraste ; 0.5 se i < ultimo_contraste ; 1.0 se nao ha contraste
   s += v * peso_prox * c ; registra contribuicao(t) = v * peso_prox * c
   peso_prox = 1.0
 score = tanh(s / sqrt(n_tokens + 1))
 label = positivo se score > 0.15 ; negativo se < -0.15 ; senao neutro
```

- O `ultimo_contraste` é calculado uma vez, antes do laço. Com vários conectivos, vale o último, o que evita o O(n²) do `fator_contraste(i, toks)` original.
- O peso do intensificador só é consumido por um termo do léxico, e não pelo token seguinte qualquer: "muito o bom" ainda amplia "bom". A exceção é a fronteira `<pont>`, que zera o peso pendente.
- Placeholders `<emo_pos>`, `<emo_neg>` e `<riso>` são entradas comuns do léxico (por exemplo +0,8, −0,8 e +0,5), e não regras especiais. `<excl>` não tem polaridade nesta versão.
- **Os limiares valem para o score após `tanh`**, o que resolve a ambiguidade do documento original.
- **A confiança no modo léxico** é |score| para positivo/negativo e 1 − |score|/0,15 para neutro. Alternativa descartada: uma confiança pseudo-probabilística (sigmoide do score). Ela pareceria mais "calibrada" do que realmente é. A forma linear é honesta e será trocada pela probabilidade do softmax no modo modelo.
- A explicação ordena as contribuições registradas por |valor| e corta em 5. O custo é desprezível, então ela é calculada só quando pedida, para não alocar a lista à toa.

### D4. Formato dos artefatos

- `lexico.tsv`: `termo<TAB>polaridade`, com polaridade em [−1, 1], `#` para comentários, UTF-8. Na carga, os termos passam pela mesma normalização da etapa [c], então o arquivo pode ter acentos. Um termo duplicado é erro de carga (pega erro de edição à mão).
- `emojis.tsv`: `simbolo<TAB>pos|neg`.
- `config.json`: `{"versao": "0.1.0", "limiar_neutro": 0.15, "max_caracteres": 5000}`. Os campos do modelo (`dim_hash`, `seed`, `conf_min`) entram na change seguinte. A carga ignora campos desconhecidos, para manter compatibilidade futura.
- Abreviações, negadores, intensificadores e conectivos ficam em código, como constantes: são listas curtas, ligadas à gramática, e mudá-las muda o contrato do pré-processamento, então precisam ser versionadas com o código.
- **Léxico semente**: 300–600 termos curados à mão (adjetivos e verbos de avaliação, gírias comuns: "top", "lixo", "show", "zoado"), criados nesta change. O OpLexicon e o SentiLex-PT não entram agora porque as licenças ainda não foram conferidas (pendência registrada no documento original). O formato TSV permite importá-los depois sem mudar código.

### D5. Modo e evolução para o modelo

`Analisador.carregar(dir)` detecta `W.npy` no diretório. Nesta change, ele sempre opera em `modo="lexico"` e ignora a presença de `W.npy`, com um aviso. A change seguinte adiciona o modo `modelo` sem mudar a assinatura pública nem o formato da saída: muda só o valor de `modo` e a origem de `confianca`.

### D6. CLI

`argparse` da biblioteca padrão. No Windows, `sys.stdin`/`sys.stdout` são reconfigurados com `reconfigure(encoding="utf-8")` na entrada do `main`, porque o console usa cp1252/cp850 por padrão. A saída usa `json.dumps(..., ensure_ascii=False)`. Os códigos de saída são: 0 para ok, 1 para alguma linha JSONL inválida e 2 para erro de uso ou de artefatos (padrão do `argparse`).

### D7. Benchmark

`bench/benchmark.py` gera um corpus sintético determinístico (seed fixa) de 10.000 textos de até 280 caracteres, combinando frases-modelo com termos do léxico, gírias, emojis e negações. Ele também aceita `--arquivo` com textos reais, um por linha. O script mede cada chamada com `time.perf_counter_ns`, depois de um aquecimento de 500 chamadas, e imprime p50/p95/p99, textos/s e o pico de RSS (via `resource` no Unix e `psutil` opcional no Windows, informando "n/d" se não estiver disponível). Um teste `pytest -m bench` falha se o p95 passar de 1 ms. Ele fica fora da suíte padrão, para não falhar em máquinas lentas.

## Risks / Trade-offs

- [Corpus sintético subestima a latência real] → o script aceita arquivo real, e a meta de 1 ms deve ser confirmada com textos reais antes de virar critério do modelo.
- [Throughput de 10.000 textos/s (100 µs/texto) pode não ser atingido em Python puro] → não é requisito desta change, só é medido e relatado. Se o pré-processamento sozinho passar de ~100 µs, isso é sinal para otimizar antes da change do modelo (fundir regex, cache LRU de tokens).
- [Léxico semente pequeno tem baixa cobertura] → é esperado: o modo léxico é o "dia 1". Os testes verificam regras (negação, contraste), não acurácia.
- [Mudar o pré-processamento depois do treino invalida o modelo] → o pré-processamento recebe testes de regressão com uma tabela de pares texto → tokens. Qualquer mudança nessa tabela exige mudança de versão em `config.json`.
- [`nada` como negador e como palavra comum ("nada a declarar")] → aceito, como no documento original. O efeito é marcar `NEG_` em termos neutros, sem impacto no score.
- [Remover acentos colapsa pares como "e"/"é"] → irrelevante para polaridade, e é o comportamento definido no documento original.

## Open Questions

- Quais termos e gírias exatos entram no léxico semente, e com que pesos? Isso é curadoria, que pode ser ajustada na implementação e depois dela sem mudar specs nem tarefas.
- O domínio de uso (avaliações, tweets, atendimento) ainda não foi definido. Ele afeta a curadoria do léxico e, sobretudo, a escolha de datasets na change de treino, mas não muda nada nesta change.
