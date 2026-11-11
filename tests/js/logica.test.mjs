// Testes da lógica pura da interface. Rode com: node --test tests/js/
import { test } from "node:test";
import assert from "node:assert/strict";

import {
  ABREVIACOES, Sequenciador, adicionarHistorico, debounce, destacar, dividirEmPartes, gerarCSV,
  normalizarPalavra, parseCSV, textosDoArquivo, textosDoCSV, textosDoTXT, tipoArquivo,
} from "../../sentimento/web/logica.js";

const destacados = (trechos) => trechos.filter((t) => t.peso !== undefined);

// --- 3.1: debounce, sequência, normalização e destaque ----------------------------

test("debounce dispara uma vez, após a última chamada", async () => {
  const chamadas = [];
  const f = debounce((x) => chamadas.push(x), 30);
  f("a"); f("ad"); f("ado");
  await new Promise((r) => setTimeout(r, 15));
  f("adorei");
  assert.deepEqual(chamadas, []);
  await new Promise((r) => setTimeout(r, 60));
  assert.deepEqual(chamadas, ["adorei"]);
});

test("debounce.cancelar impede o disparo", async () => {
  let n = 0;
  const f = debounce(() => n++, 20);
  f(); f.cancelar();
  await new Promise((r) => setTimeout(r, 50));
  assert.equal(n, 0);
});

test("Sequenciador: só o id mais recente é atual", () => {
  const s = new Sequenciador();
  const a = s.proximo();
  const b = s.proximo();
  assert.equal(s.ehAtual(a), false);
  assert.equal(s.ehAtual(b), true);
  s.invalidar();
  assert.equal(s.ehAtual(b), false);
});

test("normalizarPalavra: acentos, caixa, alongamento e abreviações", () => {
  assert.equal(normalizarPalavra("Ótimooo"), "otimo");
  assert.equal(normalizarPalavra("PÉSSIMO"), "pessimo");
  assert.equal(normalizarPalavra("Ótimo"), "otimo"); // acento decomposto
  assert.equal(normalizarPalavra("carro"), "carro");
  assert.equal(normalizarPalavra("vc"), "voce");
  assert.equal(normalizarPalavra("N"), "nao");
  assert.equal(normalizarPalavra("constructor"), "constructor"); // não confunde com Object.prototype
});

test("destacar: texto com negação", () => {
  const trechos = destacar("nao gostei do atendimento", [{ token: "NEG_gostei", peso: -0.56 }]);
  assert.deepEqual(destacados(trechos), [{ texto: "gostei", peso: -0.56, negado: true, token: "NEG_gostei" }]);
  assert.equal(trechos.map((t) => t.texto).join(""), "nao gostei do atendimento");
});

test("destacar: acento e alongamento no texto original", () => {
  const trechos = destacar("Ótimooo produto", [{ token: "otimo", peso: 0.8 }]);
  assert.deepEqual(destacados(trechos).map((t) => [t.texto, t.peso, t.negado]), [["Ótimooo", 0.8, false]]);
});

test("destacar: abreviação no texto original", () => {
  const trechos = destacar("vc n gostou", [{ token: "NEG_gostou", peso: -0.48 }]);
  assert.deepEqual(destacados(trechos).map((t) => t.texto), ["gostou"]);
});

test("destacar: token sem palavra correspondente (emoji, riso)", () => {
  const trechos = destacar("chegou 😍 kkkk", [{ token: "<emo_pos>", peso: 0.8 }, { token: "<riso>", peso: 0.5 }]);
  assert.deepEqual(destacados(trechos), []);
  assert.deepEqual(trechos, [{ texto: "chegou 😍 kkkk" }]);
});

test("destacar: palavras repetidas são todas marcadas", () => {
  const trechos = destacar("bom, bom demais", [{ token: "bom", peso: 0.9 }]);
  assert.deepEqual(destacados(trechos).map((t) => t.texto), ["bom", "bom"]);
  assert.equal(trechos.map((t) => t.texto).join(""), "bom, bom demais");
});

test("destacar: sem tokens devolve o texto inteiro", () => {
  assert.deepEqual(destacar("qualquer coisa", []), [{ texto: "qualquer coisa" }]);
  assert.deepEqual(destacar("", []), []);
});

test("destacar: mesmo base com e sem NEG_ usa o de maior peso (o primeiro)", () => {
  const trechos = destacar("bom", [{ token: "bom", peso: 0.6 }, { token: "NEG_bom", peso: -0.3 }]);
  assert.equal(destacados(trechos)[0].negado, false);
});

// --- 3.2: arquivos, partes e CSV de saída -------------------------------------------

test("tipoArquivo", () => {
  assert.equal(tipoArquivo("a.txt"), "txt");
  assert.equal(tipoArquivo("A.CSV"), "csv");
  assert.equal(tipoArquivo("relatorio.pdf"), null);
  assert.equal(tipoArquivo("semextensao"), null);
});

test(".txt: uma linha por texto, linhas em branco ignoradas, BOM e CRLF", () => {
  assert.deepEqual(textosDoTXT("﻿adorei\r\n\r\npessimo\n  \nok"), ["adorei", "pessimo", "ok"]);
});

test("parseCSV: aspas, aspas duplicadas, vírgulas e quebras de linha em campos", () => {
  const csv = 'a,b\r\n"x, y","diz ""oi""\nsegunda linha"\r\n';
  assert.deepEqual(parseCSV(csv), [["a", "b"], ["x, y", 'diz "oi"\nsegunda linha']]);
});

test("parseCSV: campo vazio e última linha sem quebra", () => {
  assert.deepEqual(parseCSV("a,,c\n1,2,"), [["a", "", "c"], ["1", "2", ""]]);
});

test("parseCSV: ponto e vírgula do Excel pt-BR", () => {
  assert.deepEqual(parseCSV("id;texto\n1;bom, mas caro"), [["id", "texto"], ["1", "bom, mas caro"]]);
});

test("CSV com cabeçalho: usa a coluna texto, inteira", () => {
  const csv = 'id,texto,data\n1,"adorei, recomendo",2026-01-01\n2,"linha1\nlinha2",2026-01-02\n';
  assert.deepEqual(textosDoCSV(csv), ["adorei, recomendo", "linha1\nlinha2"]);
});

test("CSV com cabeçalho Texto (caixa e espaços)", () => {
  assert.deepEqual(textosDoCSV("ID, Texto \n1,bom\n"), ["bom"]);
});

test("CSV sem cabeçalho texto: usa a primeira coluna de todas as linhas", () => {
  assert.deepEqual(textosDoCSV("adorei,5\npessimo,1\n\n"), ["adorei", "pessimo"]);
});

test("textosDoArquivo rejeita tipo não suportado", () => {
  assert.throws(() => textosDoArquivo("a.pdf", "x"), /não suportado/);
});

test("dividirEmPartes: 25.000 linhas viram 3 partes, na ordem", () => {
  const textos = Array.from({ length: 25000 }, (_, i) => `texto ${i}`);
  const partes = dividirEmPartes(textos);
  assert.deepEqual(partes.map((p) => p.length), [10000, 10000, 5000]);
  assert.deepEqual(partes.flat(), textos);
});

test("dividirEmPartes: limite por bytes", () => {
  const grande = "x".repeat(1000);
  const partes = dividirEmPartes(Array(10).fill(grande), 10000, 3500);
  assert.ok(partes.length > 1);
  assert.ok(partes.every((p) => p.length <= 3));
  assert.equal(partes.flat().length, 10);
});

test("dividirEmPartes: vazio", () => {
  assert.deepEqual(dividirEmPartes([]), []);
});

test("gerarCSV: cabeçalho, BOM, escape RFC 4180 e proteção contra fórmula", () => {
  const csv = gerarCSV([
    { texto: 'diz "oi", tudo\nbem', label: "positivo", score: 0.5, confianca: 0.5 },
    { texto: "=HYPERLINK(1)", label: "neutro", score: 0, confianca: 1 },
    { texto: "-bom", label: "positivo", score: 0.4, confianca: 0.4 },
  ]);
  assert.ok(csv.startsWith("﻿texto,label,score,confianca\r\n"));
  const linhas = parseCSV(csv);
  assert.deepEqual(linhas[1], ['diz "oi", tudo\nbem', "positivo", "0.5", "0.5"]);
  assert.deepEqual(linhas[2], ["'=HYPERLINK(1)", "neutro", "0", "1"]);
  assert.equal(linhas[3][0], "'-bom");
  assert.equal(linhas[3][2], "0.4"); // números não recebem apóstrofo
});

test("gerarCSV: score negativo não é protegido", () => {
  assert.ok(gerarCSV([{ texto: "ruim", label: "negativo", score: -0.4, confianca: 0.4 }]).includes("ruim,negativo,-0.4,0.4"));
});

test("adicionarHistorico: mais novo primeiro, no máximo 20", () => {
  let h = [];
  for (let i = 1; i <= 21; i++) h = adicionarHistorico(h, { texto: `t${i}` });
  assert.equal(h.length, 20);
  assert.equal(h[0].texto, "t21");
  assert.equal(h[19].texto, "t2");
});

test("ABREVIACOES é imutável", () => {
  assert.ok(Object.isFrozen(ABREVIACOES));
});
