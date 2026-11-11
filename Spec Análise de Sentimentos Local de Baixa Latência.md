# Spec: Análise de Sentimentos Local de Baixa Latência

Nov 10, 2026 · @Juan Paiva

## Visão geral e objetivos

O sistema classifica um texto curto em português como **positivo**, **negativo** ou **neutro** e devolve um score contínuo de −1 a +1, rodando 100% local em CPU com latência p95 de até 1 ms por texto.

A abordagem é deliberadamente simples: uma regressão logística sobre features de hashing, reforçada por um léxico de sentimento com regras de negação, intensidade e contraste. Não há GPU, rede neural nem chamadas de rede, e a inferência depende só de Python + NumPy.

Metas (a confirmar com benchmark na máquina-alvo):

- Latência p95 ≤ 1 ms por texto de até 280 caracteres, 1 thread
- Throughput ≥ 10.000 textos/s em lote
- Macro-F1 ≥ 0,75 nas 3 classes, no conjunto de teste
- Modelo + léxico ≤ 20 MB em disco; RAM ≤ 100 MB em execução
- Saída determinística: a mesma entrada sempre gera a mesma saída

## Requisitos

Os requisitos priorizam latência e simplicidade de implantação sobre precisão máxima.

| ID | Requisito | Critério de aceite |
| --- | --- | --- |
| RF1 | Entrada: texto UTF-8 | Até 5.000 caracteres; acima disso, truncar e sinalizar |
| RF2 | Saída estruturada | `label`, `score` (−1 a +1), `confianca` (0 a 1), `versao` |
| RF3 | Português do Brasil informal | Lida com sem acento, abreviações (vc, n, mt), emojis e alongamentos |
| RF4 | Processamento em lote | `analisar_lote(lista)` vetorizado |
| RF5 | Explicabilidade | Opcional: top 5 tokens que mais pesaram na decisão |
| RF6 | Front end web local | Página única com análise ao vivo, modo lote e destaque de tokens (seção Front end) |
| RNF1 | Latência | p95 ≤ 1 ms por texto (≤ 280 caracteres), 1 thread; ≤ 50 ms de ida e volta na interface |
| RNF2 | Memória | ≤ 100 MB de RAM; artefatos ≤ 20 MB |
| RNF3 | Offline | Nenhuma chamada de rede na inferência nem na interface |
| RNF4 | Dependências | Inferência: Python 3.10+ e NumPy. Treino: + scikit-learn |
| RNF5 | Determinismo | Hash com seed fixa; mesma entrada, mesma saída |
| RNF6 | Portabilidade | Linux, macOS e Windows, x86-64 e ARM64 |

## Arquitetura

Duas vias leves saem do mesmo pré-processamento: hashing de n-gramas e um score léxico com regras. Ambas alimentam uma única regressão logística.

&#91;embedded content: arquitetura · 7 etapas, 1 via de fallback\]

A linha tracejada é o modo fallback: sem modelo treinado, o score léxico decide sozinho.

## Pré-processamento

O mesmo pipeline roda no treino e na inferência; qualquer divergência entre os dois derruba a precisão silenciosamente. Todas as regex são pré-compiladas no carregamento.

1. **Normalização:** Unicode NFKC, minúsculas, remoção de acentos (usuários escrevem "nao" e "pessimo").
2. **Substituições:** URLs → `<url>`, @menções → `<user>`, números → `<num>`.
3. **Emojis e emoticons:** tabela fixa mapeia para `<emo_pos>` ou `<emo_neg>` (ex.: 😍 e `:)` → positivo; 😡 e `:(` → negativo).
4. **Alongamentos:** 3+ letras repetidas viram 1 ("muuuito" → "muito") e marcam a flag `alongado`.
5. **Abreviações:** dicionário curto (vc → voce, n → nao, mt/mto → muito, tb → tambem, nd → nada).
6. **Tokenização:** regex `\w+|<\w+>|!+|\?+`; `!` repetido vira o token `<excl>`.
7. **Negação:** após um negador (nao, nunca, nem, jamais, nada, ninguem), os próximos tokens até a pontuação, no máximo 3, recebem o prefixo `NEG_` ("nao gostei" → `nao NEG_gostei`).
8. **Intensidade:** intensificadores (muito, super, demais, extremamente) multiplicam o próximo termo do léxico por 1,5; atenuadores (pouco, meio, quase) por 0,5.
9. **Contraste:** após "mas", "porem", "entretanto" ou "contudo", os termos seguintes pesam 1,5 e os anteriores 0,5 no score léxico.

## Algoritmo

A decisão vem de uma regressão logística multinomial sobre um vetor esparso de hashing (2^18 dimensões) mais 3 features densas do léxico. O score final é a diferença entre as probabilidades de positivo e negativo.

```latex
\hat{p} = \mathrm{softmax}(W x + b), \qquad s = \hat{p}_{pos} - \hat{p}_{neg} \in [-1, 1]
```

**Features:**

- Hashing de unigramas e bigramas (já com `NEG_`), MurmurHash3 32 bits com seed fixa, sinal pelo bit alto para reduzir colisões
- Score léxico (tanh da soma ponderada), contagem de termos positivos e contagem de negativos

**Pseudocódigo da inferência:**

```python
def analisar(texto):
    toks = preprocessar(texto)                 # seção Pré-processamento
    idx, val = hash_features(toks, dim=2**18)  # uni + bigramas, esparso
    lex = features_lexicas(toks)               # [score, n_pos, n_neg]
    z = W[:, idx] @ val + W_lex @ lex + b      # 3 logits
    p = softmax(z)
    score = p[POS] - p[NEG]
    label = argmax(p)
    if p[label] < CONF_MIN:                    # ajustado na validação
        label = NEUTRO
    return label, score, p[label]

def features_lexicas(toks):
    s, peso, n_pos, n_neg = 0.0, 1.0, 0, 0
    for i, t in enumerate(toks):
        if t in INTENSIF:                      # muito=1.5, pouco=0.5
            peso = INTENSIF[t]; continue
        neg = t.startswith("NEG_")
        v = LEXICO.get(t[4:] if neg else t, 0.0)
        if neg:
            v = -0.8 * v                       # inverte e atenua
        s += v * peso * fator_contraste(i, toks)
        n_pos += v > 0; n_neg += v < 0
        peso = 1.0
    return [tanh(s / sqrt(len(toks) + 1)), n_pos, n_neg]
```

**Modo fallback (sem modelo treinado):** usa só o score léxico, com positivo se s > 0,15, negativo se s < −0,15, senão neutro. Serve para o dia 1 e para testes de fumaça.

**Por que é rápido:** inferência = tokenizar + algumas dezenas de hashes + um produto de 3 linhas da matriz W por um vetor esparso; tudo O(n) no tamanho do texto, sem alocação de matriz densa.

## Treinamento e avaliação

O modelo é treinado uma vez, offline, com dados públicos em PT-BR e, de preferência, uma amostra rotulada do seu próprio domínio. Licenças e tamanhos dos conjuntos abaixo ainda precisam ser conferidos.

| Recurso | Tipo | Uso |
| --- | --- | --- |
| TweetSentBR | Tweets rotulados em 3 classes | Treino e teste de texto informal |
| B2W-Reviews01 | Avaliações de e-commerce com nota | Treino: nota 1–2 negativo, 3 neutro, 4–5 positivo |
| Olist (Brazilian E-Commerce) | Avaliações com nota 1–5 | Treino, mesmo mapeamento de notas |
| OpLexicon / SentiLex-PT | Léxicos de polaridade | Base do `LEXICO`, revisado à mão para o domínio |
| Amostra do domínio | 300–500 textos rotulados por você | Validação final e ajuste de limiares |

**Procedimento:**

1. Aplicar o pré-processamento e deduplicar os textos.
2. Dividir 80/10/10 estratificado por classe.
3. Treinar `LogisticRegression` multinomial, L2, `class_weight="balanced"`, buscando C em {0,5; 1; 2; 4}.
4. Ajustar `CONF_MIN` e o limiar do fallback na validação, maximizando macro-F1.
5. Exportar `W` e `b` como float32 em `.npy`, junto com o `config.json`.

**Critérios de aceite:**

- [ ] Macro-F1 ≥ 0,75 no teste e ≥ 0,70 na amostra do domínio
- [ ] Modelo supera o fallback só-léxico em pelo menos 10 pontos de macro-F1
- [ ] Latência p50/p95/p99 medida em 10.000 textos, p95 ≤ 1 ms
- [ ] Matriz de confusão revisada; erros de negação e ironia catalogados

## Front end

O pacote inclui uma interface web local: uma página única em HTML + JavaScript puro, servida pelo próprio processo em `127.0.0.1`, que analisa o texto enquanto a pessoa digita. Sem build, sem framework e sem CDN, para funcionar offline.

**Componentes da tela:**

| Componente | Comportamento |
| --- | --- |
| Campo de texto | Análise ao vivo com debounce de 150 ms; Ctrl+Enter força a análise |
| Resultado | Rótulo com ícone e cor (positivo, negativo, neutro), confiança em % e latência em ms |
| Barra de score | Escala de −1 a +1 com marcador na posição do score |
| Destaque de tokens | Palavras que mais pesaram sublinhadas em verde ou vermelho; negação marcada (usa RF5) |
| Modo lote | Upload de .txt (uma linha por texto) ou .csv; tabela de resultados e botão para baixar CSV |
| Histórico | Últimas 20 análises da sessão, só em memória, com opção de limpar |
| Rodapé | Versão do modelo e status (modelo carregado ou fallback léxico) |

**API local consumida pela página:**

| Método | Rota | Corpo / resposta |
| --- | --- | --- |
| POST | `/api/analisar` | `{"texto": "...", "explicar": true}` → resultado + tokens com peso |
| POST | `/api/lote` | `{"textos": [...]}` → lista de resultados; até 10.000 itens |
| GET | `/api/saude` | Versão, modo (modelo ou fallback), latência p95 recente |
| GET | `/` | A página estática |

**Requisitos do front end:**

- Servidor: stdlib (`http.server`) por padrão, FastAPI + uvicorn como opção; inicia com `sentimento serve --porta 8080`
- Escuta só em `127.0.0.1`; nenhum texto é gravado em disco nem enviado para fora
- Ida e volta na página com p95 ≤ 50 ms para um texto curto
- Página + scripts + CSS ≤ 100 KB, embutidos no pacote
- Acessível: cor nunca é o único indicador (rótulo em texto + ícone), navegação por teclado, contraste AA, tema claro e escuro
- Requisição anterior cancelada com `AbortController` quando o texto muda, para não exibir resultado velho

## Interface, desempenho e limitações

O pacote expõe uma classe Python e uma CLI; os artefatos do modelo ficam numa pasta versionada.

```python
from sentimento import Analisador

a = Analisador.carregar("modelo/")
a.analisar("o produto chegou rapido, adorei!")
# {"label": "positivo", "score": 0.87, "confianca": 0.91, "versao": "1.0.0"}
a.analisar_lote(textos)   # lista de dicts
```

CLI: `sentimento "texto"` ou JSONL via stdin → JSONL na stdout.

**Artefatos em `modelo/`:** `W.npy`, `b.npy`, `lexico.tsv`, `emojis.tsv`, `config.json` (dimensão do hash, seed, `CONF_MIN`, versão).

**Regras de desempenho:**

- Inferência sem scikit-learn: só NumPy, com `W` carregado via `np.load(mmap_mode="r")`
- Regex pré-compiladas e cache LRU de hash por token (10.000 entradas)
- Lote: concatenar índices esparsos e fazer um único produto matricial
- Benchmark no CI com 10.000 textos reais; falha se p95 passar de 1 ms

**Limitações conhecidas:**

- Ironia e sarcasmo ("que ótimo, atrasou de novo") tendem a sair como positivo
- Sentimento misto vira um único rótulo; textos longos diluem o score
- Fora do domínio de treino, a precisão cai; retreinar com amostra local resolve a maior parte
- Só português; outros idiomas saem quase sempre como neutro

Se a precisão não bastar, o próximo passo é um transformer pequeno quantizado (ex.: ONNX int8), aceitando latência de alguns milissegundos.
