#!/usr/bin/env node
// Confere o dicionário de inglês contra o código.
//
// As chaves do dicionário são o próprio texto em português (ver src/lib/i18n.ts),
// então dá para descobrir o que falta traduzir lendo as chamadas `t("…")`,
// `tr("…")` e `traduzir(lang, "…")` no código-fonte.
//
// Uso:
//   node scripts/checar-i18n.mjs          # lista o que falta (sai 0)
//   node scripts/checar-i18n.mjs --falhar # sai 1 se faltar alguma tradução
//
// Chaves montadas em tempo de execução (t(item.label)) não aparecem aqui: elas
// vêm de listas cujos rótulos estão no dicionário, e o fallback em português
// garante que nada quebre.
import { readdirSync, readFileSync, statSync } from "node:fs";
import { dirname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const raiz = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const fonte = join(raiz, "src");

function arquivos(dir) {
  const saida = [];
  for (const nome of readdirSync(dir)) {
    const caminho = join(dir, nome);
    if (statSync(caminho).isDirectory()) {
      if (nome === "assets" || nome === "node_modules") continue;
      saida.push(...arquivos(caminho));
    } else if (/\.(ts|tsx)$/.test(nome) && !nome.endsWith(".test.ts")) {
      saida.push(caminho);
    }
  }
  return saida;
}

/// Chamadas com o texto como primeiro argumento literal.
const CHAMADA = /\b(?:t|tr|traduzir)\(\s*(?:[A-Za-z_$][\w$]*\s*,\s*)?("(?:[^"\\]|\\.)*"|`(?:[^`\\$]|\\.)*`)/g;

/// Entradas do dicionário: a chave é o texto antes dos dois-pontos (com aspas
/// quando tem espaço ou pontuação; sem aspas quando é uma palavra só).
const ENTRADA = /^\s*(?:"((?:[^"\\]|\\.)*)"|([A-Za-z\u00C0-\u024F_$][\w$\u00C0-\u024F]*))\s*:/gm;

function semAspas(literal) {
  return literal.slice(1, -1).replace(/\\(["'`\\])/g, "$1");
}

const i18n = readFileSync(join(fonte, "lib", "i18n.ts"), "utf8");
const blocoEn = i18n.slice(i18n.indexOf("const EN: Record<string, string> = {"));
const traduzidas = new Set();
for (const achado of blocoEn.matchAll(ENTRADA)) {
  traduzidas.add((achado[1] ?? achado[2]).replace(/\\(["'`\\])/g, "$1"));
}

const usadas = new Map(); // chave -> arquivos
for (const caminho of arquivos(fonte)) {
  const texto = readFileSync(caminho, "utf8");
  for (const achado of texto.matchAll(CHAMADA)) {
    const chave = semAspas(achado[1]);
    // Chaves de exemplo/troca de mensagem não são texto de tela.
    if (!chave.trim() || chave.includes("\n")) continue;
    if (!usadas.has(chave)) usadas.set(chave, new Set());
    usadas.get(chave).add(relative(raiz, caminho));
  }
}

const faltando = [...usadas.entries()]
  .filter(([chave]) => !traduzidas.has(chave))
  .sort(([a], [b]) => a.localeCompare(b, "pt-BR"));

const sobrando = [...traduzidas]
  .filter((chave) => !usadas.has(chave))
  .sort((a, b) => a.localeCompare(b, "pt-BR"));

console.log(`chaves usadas no código: ${usadas.size}`);
console.log(`chaves traduzidas: ${traduzidas.size}`);

if (faltando.length === 0) {
  console.log("\n✓ nenhum texto sem tradução");
} else {
  console.log(`\n${faltando.length} texto(s) sem tradução:\n`);
  for (const [chave, onde] of faltando) {
    console.log(`  ${JSON.stringify(chave)}`);
    console.log(`      ${[...onde].join(", ")}`);
  }
}

if (sobrando.length > 0) {
  console.log(`\n${sobrando.length} tradução(ões) sem uso no código (pode ser chave indireta):\n`);
  for (const chave of sobrando) console.log(`  ${JSON.stringify(chave)}`);
}

if (process.argv.includes("--falhar") && faltando.length > 0) process.exit(1);
