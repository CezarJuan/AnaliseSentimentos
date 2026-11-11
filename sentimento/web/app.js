// Interface: DOM, eventos e fetch. A lógica testável fica em logica.js.
// Regra de segurança: texto do usuário só entra no DOM via textContent (nunca innerHTML).
import {
  Sequenciador, adicionarHistorico, debounce, destacar, dividirEmPartes, gerarCSV,
  textosDoArquivo, tipoArquivo, PREFIXO_NEG,
} from "./logica.js";

const $ = (id) => document.getElementById(id);
const el = {
  texto: $("texto"), analisar: $("analisar"), resultado: $("resultado"),
  vazio: $("resultado-vazio"), conteudo: $("resultado-conteudo"), erro: $("erro"),
  rotulo: $("rotulo"), rotuloIcone: $("rotulo-icone"), rotuloTexto: $("rotulo-texto"),
  confianca: $("confianca"), score: $("score"), latencia: $("latencia"),
  barra: $("barra"), marcador: $("marcador"), destaque: $("destaque"), tokens: $("tokens"),
  anuncio: $("anuncio"), arquivo: $("arquivo"), baixar: $("baixar"), loteStatus: $("lote-status"),
  tabelaBloco: $("tabela-bloco"), tabelaCorpo: document.querySelector("#tabela tbody"),
  limpar: $("limpar"), historico: $("historico"), historicoVazio: $("historico-vazio"),
  status: $("status"), tema: $("tema"),
};

const ROTULOS = { positivo: "Positivo", negativo: "Negativo", neutro: "Neutro" };
const ICONES = { positivo: "▲", negativo: "▼", neutro: "●" };
const MODOS = { lexico: "léxico (fallback)", modelo: "modelo carregado" };
const PLACEHOLDERS = {
  "<emo_pos>": "emoji positivo", "<emo_neg>": "emoji negativo", "<riso>": "risada",
  "<url>": "link", "<user>": "menção", "<num>": "número",
};
const MAX_LINHAS_TABELA = 1000;
const MSG_FORA = "O servidor não está respondendo. Verifique se \"sentimento serve\" está rodando.";

const fmtNum = (n, casas = 2) => n.toLocaleString("pt-BR", { minimumFractionDigits: casas, maximumFractionDigits: casas });
const fmtPct = (c) => `${Math.round(c * 100)}%`;
const sinal = (p) => (p > 0 ? "+" : "−");

class ErroServidor extends Error {}

async function postJSON(rota, corpo, signal) {
  let resposta;
  try {
    resposta = await fetch(rota, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(corpo),
      signal,
    });
  } catch (e) {
    if (e.name === "AbortError") throw e;
    marcarStatus(null);
    throw new ErroServidor(MSG_FORA);
  }
  let dados = null;
  try { dados = await resposta.json(); } catch { /* corpo não-JSON */ }
  if (!resposta.ok) throw new ErroServidor(dados?.erro || `Erro ${resposta.status} do servidor.`);
  return dados;
}

// --- Análise ao vivo (D5) ------------------------------------------------------------------

const seq = new Sequenciador();
let controlador = null;
let historico = [];

const agendar = debounce(() => analisar({ confirmar: false }));

async function analisar({ confirmar }) {
  agendar.cancelar();
  const texto = el.texto.value;
  controlador?.abort();
  controlador = null;
  if (texto.trim() === "") {
    seq.invalidar();
    limparResultado();
    return;
  }
  const id = seq.proximo();
  const atual = new AbortController();
  controlador = atual;
  const t0 = performance.now();
  try {
    const r = await postJSON("/api/analisar", { texto, explicar: true }, atual.signal);
    // Só exibe se esta ainda é a requisição mais recente e o texto não mudou.
    if (!seq.ehAtual(id) || el.texto.value !== texto) return;
    renderizar(texto, r, performance.now() - t0);
    marcarStatus(true);
    if (confirmar) {
      historico = adicionarHistorico(historico, { texto, label: r.label, score: r.score });
      renderizarHistorico();
    }
  } catch (e) {
    if (e.name === "AbortError" || !seq.ehAtual(id)) return;
    mostrarErro(e.message);
  } finally {
    if (controlador === atual) controlador = null;
  }
}

function limparResultado() {
  el.resultado.classList.add("vazio");
  el.resultado.classList.remove("desatualizado");
  el.conteudo.hidden = true;
  el.vazio.hidden = false;
  el.erro.hidden = true;
  el.anuncio.textContent = "";
}

function mostrarErro(mensagem) {
  el.erro.textContent = mensagem;
  el.erro.hidden = false;
  el.resultado.classList.add("desatualizado"); // mantém o último resultado, esmaecido
}

function renderizar(texto, r, idaVoltaMs) {
  el.resultado.classList.remove("vazio", "desatualizado");
  el.erro.hidden = true;
  el.vazio.hidden = true;
  el.conteudo.hidden = false;

  el.rotulo.className = `rotulo ${r.label}`;
  el.rotuloIcone.textContent = ICONES[r.label];
  el.rotuloTexto.textContent = ROTULOS[r.label];
  el.confianca.textContent = fmtPct(r.confianca);
  el.score.textContent = (r.score > 0 ? "+" : "") + fmtNum(r.score);
  el.latencia.textContent = `${fmtNum(idaVoltaMs, 1)} ms`;

  el.marcador.style.left = `${((r.score + 1) / 2) * 100}%`;
  el.barra.setAttribute("aria-valuenow", String(r.score));
  el.barra.setAttribute("aria-valuetext", `${fmtNum(r.score)}, ${ROTULOS[r.label].toLowerCase()}`);

  renderizarDestaque(texto, r.tokens || []);
  el.anuncio.textContent = `${ROTULOS[r.label]}, confiança ${fmtPct(r.confianca)}`;
}

function nomeToken(token) {
  const negado = token.startsWith(PREFIXO_NEG);
  const base = negado ? token.slice(PREFIXO_NEG.length) : token;
  return { nome: PLACEHOLDERS[base] || base, negado };
}

function renderizarDestaque(texto, tokens) {
  const frag = document.createDocumentFragment();
  for (const t of destacar(texto, tokens)) {
    if (t.peso === undefined) { frag.append(t.texto); continue; }
    const polo = t.peso > 0 ? "pos" : "neg";
    const mark = document.createElement("mark");
    mark.className = polo + (t.negado ? " negado" : "");
    const descricao = `${t.peso > 0 ? "positivo" : "negativo"}${t.negado ? ", negado" : ""}, peso ${fmtNum(t.peso)}`;
    mark.title = descricao;
    mark.append(t.texto);
    const s = document.createElement("span");
    s.className = "sinal";
    s.setAttribute("aria-hidden", "true");
    s.textContent = sinal(t.peso) + (t.negado ? "¬" : "");
    const leitor = document.createElement("span");
    leitor.className = "so-leitor";
    leitor.textContent = ` (${descricao})`;
    mark.append(s, leitor);
    frag.append(mark);
  }
  el.destaque.replaceChildren(frag);

  const itens = tokens.map(({ token, peso }) => {
    const { nome, negado } = nomeToken(token);
    const li = document.createElement("li");
    li.className = peso > 0 ? "pos" : "neg";
    const p = document.createElement("span");
    p.className = "peso";
    p.textContent = sinal(peso) + fmtNum(Math.abs(peso));
    const n = document.createElement("span");
    n.textContent = nome;
    li.append(p, n);
    if (negado) {
      const selo = document.createElement("span");
      selo.className = "selo";
      selo.textContent = "negado";
      li.append(selo);
    }
    return li;
  });
  if (!itens.length) {
    const li = document.createElement("li");
    li.textContent = "Nenhum termo do léxico encontrado.";
    itens.push(li);
  }
  el.tokens.replaceChildren(...itens);
}

el.texto.addEventListener("input", () => {
  if (el.texto.value.trim() === "") analisar({ confirmar: false });
  else agendar();
});
el.texto.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
    e.preventDefault();
    analisar({ confirmar: true });
  }
});
el.analisar.addEventListener("click", () => analisar({ confirmar: true }));

// --- Histórico (D8) -----------------------------------------------------------------------

function renderizarHistorico() {
  el.historicoVazio.hidden = historico.length > 0; // "Limpar" fica sempre focável (ordem de Tab)
  el.historico.replaceChildren(...historico.map((item) => {
    const li = document.createElement("li");
    const b = document.createElement("button");
    b.type = "button";
    b.title = "Analisar este texto de novo";
    const t = document.createElement("span");
    t.className = "texto-item";
    t.textContent = item.texto;
    const e = document.createElement("span");
    e.className = `etiqueta ${item.label}`;
    e.textContent = `${ICONES[item.label]} ${ROTULOS[item.label]} ${item.score > 0 ? "+" : ""}${fmtNum(item.score)}`;
    b.append(t, e);
    b.addEventListener("click", () => {
      el.texto.value = item.texto;
      el.texto.focus();
      analisar({ confirmar: false });
    });
    li.append(b);
    return li;
  }));
}

el.limpar.addEventListener("click", () => {
  historico = [];
  renderizarHistorico();
});

// --- Lote (D7) -------------------------------------------------------------------------------

let ultimoLote = [];
let nomeLote = "resultado";

el.arquivo.addEventListener("change", async () => {
  const arquivo = el.arquivo.files[0];
  el.arquivo.value = ""; // permite escolher o mesmo arquivo de novo
  if (!arquivo) return;
  if (!tipoArquivo(arquivo.name)) {
    el.loteStatus.textContent = `"${arquivo.name}": tipo não suportado. Use um arquivo .txt ou .csv.`;
    return;
  }
  let textos;
  try {
    textos = textosDoArquivo(arquivo.name, await arquivo.text());
  } catch (e) {
    el.loteStatus.textContent = e.message;
    return;
  }
  if (!textos.length) {
    el.loteStatus.textContent = `"${arquivo.name}" não tem nenhum texto.`;
    return;
  }
  await processarLote(arquivo.name, textos);
});

async function processarLote(nome, textos) {
  const partes = dividirEmPartes(textos);
  const resultados = [];
  el.arquivo.disabled = true;
  el.baixar.disabled = true;
  const t0 = performance.now();
  try {
    for (const [i, parte] of partes.entries()) {
      el.loteStatus.textContent = partes.length > 1
        ? `Analisando parte ${i + 1} de ${partes.length} (${resultados.length.toLocaleString("pt-BR")} de ${textos.length.toLocaleString("pt-BR")} textos)…`
        : `Analisando ${textos.length.toLocaleString("pt-BR")} textos…`;
      const r = await postJSON("/api/lote", { textos: parte });
      resultados.push(...r.resultados);
    }
  } catch (e) {
    el.loteStatus.textContent = `Lote interrompido: ${e.message}`;
    return;
  } finally {
    el.arquivo.disabled = false;
  }
  marcarStatus(true);
  ultimoLote = textos.map((texto, i) => ({ texto, ...resultados[i] }));
  nomeLote = nome.replace(/\.[^.]+$/, "") + "-sentimentos";
  const segundos = (performance.now() - t0) / 1000;
  const total = ultimoLote.length.toLocaleString("pt-BR");
  el.loteStatus.textContent = ultimoLote.length > MAX_LINHAS_TABELA
    ? `${total} textos analisados em ${fmtNum(segundos, 1)} s. Mostrando ${MAX_LINHAS_TABELA.toLocaleString("pt-BR")} de ${total}; o CSV tem todos.`
    : `${total} textos analisados em ${fmtNum(segundos, 1)} s.`;
  renderizarTabela();
  el.baixar.disabled = false;
}

function renderizarTabela() {
  const linhas = ultimoLote.slice(0, MAX_LINHAS_TABELA).map((r) => {
    const tr = document.createElement("tr");
    const celula = (conteudo, classe) => {
      const td = document.createElement("td");
      if (classe) td.className = classe;
      td.textContent = conteudo;
      return td;
    };
    tr.append(
      celula(r.texto),
      celula(`${ICONES[r.label]} ${ROTULOS[r.label]}`, `etiqueta ${r.label}`),
      celula(fmtNum(r.score), "num"),
      celula(fmtPct(r.confianca), "num"),
    );
    return tr;
  });
  el.tabelaCorpo.replaceChildren(...linhas);
  el.tabelaBloco.hidden = false;
}

el.baixar.addEventListener("click", () => {
  const blob = new Blob([gerarCSV(ultimoLote)], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${nomeLote}.csv`;
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
});

// --- Rodapé: saúde do servidor ------------------------------------------------------------------

let ultimaSaude = null;

function marcarStatus(online) {
  if (online === null) {
    el.status.textContent = MSG_FORA;
    el.status.classList.add("fora");
  } else if (ultimaSaude) {
    el.status.textContent = `Versão ${ultimaSaude.versao} · ${MODOS[ultimaSaude.modo] || ultimaSaude.modo}`;
    el.status.classList.remove("fora");
  }
}

async function verificarSaude() {
  try {
    const r = await fetch("/api/saude", { cache: "no-store" });
    if (!r.ok) throw new Error();
    ultimaSaude = await r.json();
    marcarStatus(true);
  } catch {
    marcarStatus(null);
  }
}

// --- Tema (só a preferência vai para o localStorage) -------------------------------------------------

const CHAVE_TEMA = "sentimento-tema";
const escuroSistema = window.matchMedia("(prefers-color-scheme: dark)");

function temaEfetivo() {
  return document.documentElement.dataset.theme || (escuroSistema.matches ? "dark" : "light");
}

function aplicarTema(tema) {
  if (tema === "dark" || tema === "light") document.documentElement.dataset.theme = tema;
  else delete document.documentElement.dataset.theme;
  el.tema.textContent = temaEfetivo() === "dark" ? "Usar tema claro" : "Usar tema escuro";
}

el.tema.addEventListener("click", () => {
  const novo = temaEfetivo() === "dark" ? "light" : "dark";
  aplicarTema(novo);
  try { localStorage.setItem(CHAVE_TEMA, novo); } catch { /* armazenamento indisponível */ }
});
escuroSistema.addEventListener("change", () => aplicarTema(document.documentElement.dataset.theme));

// --- Início ----------------------------------------------------------------------------------------

let temaSalvo = null;
try { temaSalvo = localStorage.getItem(CHAVE_TEMA); } catch { /* armazenamento indisponível */ }
aplicarTema(temaSalvo);
renderizarHistorico();
verificarSaude();
setInterval(verificarSaude, 10000);
