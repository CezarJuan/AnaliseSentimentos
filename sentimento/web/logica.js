// Lógica pura da interface (sem DOM e sem fetch): testada com `node --test tests/js/`.
// Ver design.md da change interface-web, decisões D5–D8.

export const DEBOUNCE_MS = 150;
export const MAX_HISTORICO = 20;
export const MAX_LOTE = 10000;
export const MAX_BYTES_PARTE = 8 * 1024 * 1024;
export const PREFIXO_NEG = "NEG_";

// Espelho de sentimento/preprocessamento.py: ABREVIACOES (teste de paridade em tests/test_js.py).
export const ABREVIACOES = Object.freeze({
  vc: "voce", vcs: "voces", n: "nao", mt: "muito", mto: "muito", mta: "muita",
  tb: "tambem", tbm: "tambem", nd: "nada", pq: "porque", td: "tudo", msm: "mesmo",
  blz: "beleza", obg: "obrigado", vlw: "valeu",
});

// --- Tempo -----------------------------------------------------------------------

export function debounce(fn, ms = DEBOUNCE_MS) {
  let timer = null;
  const chamado = (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => { timer = null; fn(...args); }, ms);
  };
  chamado.cancelar = () => { clearTimeout(timer); timer = null; };
  return chamado;
}

// Garante que só a resposta da requisição mais recente seja exibida (D5).
export class Sequenciador {
  #atual = 0;
  proximo() { return ++this.#atual; }
  ehAtual(id) { return id === this.#atual; }
  invalidar() { this.#atual++; }
}

// --- Normalização e destaque (D6) -----------------------------------------------

const RE_MARCAS = /\p{Mn}/gu;
const RE_ALONGAMENTO = /(\p{L})\1{2,}/gu;
const RE_PALAVRA = /[\p{L}\p{M}\p{N}_]+/gu; // \p{M}: acentos em forma decomposta (NFD)

export function normalizarPalavra(palavra) {
  const base = palavra.normalize("NFKC").toLowerCase().normalize("NFD").replace(RE_MARCAS, "");
  const reduzida = base.replace(RE_ALONGAMENTO, "$1");
  return Object.hasOwn(ABREVIACOES, reduzida) ? ABREVIACOES[reduzida] : reduzida;
}

/**
 * Divide `texto` em trechos; os que correspondem a um token explicado recebem peso e negação.
 * @param {string} texto
 * @param {{token: string, peso: number}[]} tokens  (ordenados por |peso|, como a API devolve)
 * @returns {{texto: string, peso?: number, negado?: boolean, token?: string}[]}
 */
export function destacar(texto, tokens) {
  const porBase = new Map();
  for (const { token, peso } of tokens || []) {
    if (token.startsWith("<")) continue; // placeholders (<emo_pos>, <riso>...) não têm palavra
    const negado = token.startsWith(PREFIXO_NEG);
    const base = negado ? token.slice(PREFIXO_NEG.length) : token;
    if (!porBase.has(base)) porBase.set(base, { peso, negado, token });
  }
  const trechos = [];
  let fim = 0;
  const empurrarTexto = (t) => {
    if (!t) return;
    const ultimo = trechos[trechos.length - 1];
    if (ultimo && ultimo.peso === undefined) ultimo.texto += t;
    else trechos.push({ texto: t });
  };
  for (const m of texto.matchAll(RE_PALAVRA)) {
    const info = porBase.size ? porBase.get(normalizarPalavra(m[0])) : undefined;
    if (!info) continue;
    empurrarTexto(texto.slice(fim, m.index));
    trechos.push({ texto: m[0], ...info });
    fim = m.index + m[0].length;
  }
  empurrarTexto(texto.slice(fim));
  return trechos;
}

// --- Arquivos de lote (D7) --------------------------------------------------------

export function tipoArquivo(nome) {
  const m = /\.([^.]+)$/.exec(nome || "");
  const ext = m ? m[1].toLowerCase() : "";
  return ext === "txt" || ext === "csv" ? ext : null;
}

const semBOM = (t) => (t.charCodeAt(0) === 0xfeff ? t.slice(1) : t);

export function textosDoTXT(conteudo) {
  return semBOM(conteudo).split(/\r?\n/).filter((l) => l.trim() !== "");
}

function detectarDelimitador(conteudo) {
  // Excel em pt-BR salva CSV com ";". Conta delimitadores fora de aspas na primeira linha.
  let virgulas = 0, pontoVirgulas = 0, aspas = false;
  for (const c of conteudo) {
    if (c === '"') aspas = !aspas;
    else if (!aspas && (c === "\n" || c === "\r")) break;
    else if (!aspas && c === ",") virgulas++;
    else if (!aspas && c === ";") pontoVirgulas++;
  }
  return pontoVirgulas > virgulas ? ";" : ",";
}

/** Parser RFC 4180: aspas, aspas duplicadas, delimitador e quebras de linha dentro de campos. */
export function parseCSV(conteudo, delimitador) {
  const texto = semBOM(conteudo);
  const sep = delimitador || detectarDelimitador(texto);
  const linhas = [];
  let linha = [], campo = "", aspas = false, i = 0;
  while (i < texto.length) {
    const c = texto[i];
    if (aspas) {
      if (c === '"' && texto[i + 1] === '"') { campo += '"'; i += 2; continue; }
      if (c === '"') { aspas = false; i++; continue; }
      campo += c; i++; continue;
    }
    if (c === '"' && campo === "") { aspas = true; i++; continue; }
    if (c === sep) { linha.push(campo); campo = ""; i++; continue; }
    if (c === "\r" || c === "\n") {
      linha.push(campo); linhas.push(linha); linha = []; campo = "";
      i += c === "\r" && texto[i + 1] === "\n" ? 2 : 1;
      continue;
    }
    campo += c; i++;
  }
  if (campo !== "" || linha.length) { linha.push(campo); linhas.push(linha); }
  return linhas;
}

export function textosDoCSV(conteudo) {
  const linhas = parseCSV(conteudo).filter((l) => l.some((c) => c.trim() !== ""));
  if (!linhas.length) return [];
  const coluna = linhas[0].findIndex((c) => c.trim().toLowerCase() === "texto");
  const dados = coluna >= 0 ? linhas.slice(1) : linhas;
  const col = coluna >= 0 ? coluna : 0;
  return dados.map((l) => l[col] ?? "").filter((t) => t.trim() !== "");
}

export function textosDoArquivo(nome, conteudo) {
  const tipo = tipoArquivo(nome);
  if (tipo === "txt") return textosDoTXT(conteudo);
  if (tipo === "csv") return textosDoCSV(conteudo);
  throw new Error(`Tipo de arquivo não suportado: use .txt ou .csv`);
}

const codificador = new TextEncoder();

/** Divide em partes de até `maxItens` textos e ~`maxBytes` de JSON, preservando a ordem. */
export function dividirEmPartes(textos, maxItens = MAX_LOTE, maxBytes = MAX_BYTES_PARTE) {
  const partes = [];
  let atual = [], bytes = 0;
  for (const t of textos) {
    const tamanho = codificador.encode(JSON.stringify(t)).length + 1;
    if (atual.length && (atual.length >= maxItens || bytes + tamanho > maxBytes)) {
      partes.push(atual); atual = []; bytes = 0;
    }
    atual.push(t); bytes += tamanho;
  }
  if (atual.length) partes.push(atual);
  return partes;
}

// --- CSV de saída ---------------------------------------------------------------------

function campoCSV(valor, protegerFormula) {
  let v = String(valor);
  // Evita que o Excel interprete o texto do usuário como fórmula (=, +, -, @).
  if (protegerFormula && /^[=+\-@\t\r]/.test(v)) v = "'" + v;
  return /[",\r\n;]|^\s|\s$/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v;
}

export function gerarCSV(linhas) {
  const corpo = linhas.map((l) =>
    [campoCSV(l.texto, true), campoCSV(l.label, true), String(l.score), String(l.confianca)].join(","));
  return "﻿" + ["texto,label,score,confianca", ...corpo].join("\r\n") + "\r\n";
}

// --- Histórico (D8) ----------------------------------------------------------------------

export function adicionarHistorico(lista, item, max = MAX_HISTORICO) {
  return [item, ...lista].slice(0, max);
}
