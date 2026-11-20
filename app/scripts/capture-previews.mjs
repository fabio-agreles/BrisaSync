#!/usr/bin/env node
// Captura as prévias usadas no README e no metainfo do Flatpak.
//
// Roda contra o build web em modo demonstração (dados simulados), então não
// precisa de rclone nem de contas reais:
//
//   npm run build && npx vite preview --port 4173 &
//   NODE_PATH=…/node_modules node scripts/capture-previews.mjs
//
// O `playwright-core` não é dependência do app (é ferramenta de
// desenvolvimento): aponte NODE_PATH para onde ele estiver instalado ou passe
// PLAYWRIGHT_CORE=/caminho/para/playwright-core.
import { mkdir } from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import { pathToFileURL } from "node:url";

const BASE = process.env.PREVIEW_URL ?? "http://localhost:4173";
const OUT = process.env.PREVIEW_DIR ?? path.join("docs", "previews");
// 1240x900 @2x = 2480x1800, o tamanho que o metainfo declara.
const VIEWPORT = { width: 1240, height: 900 };
const SCALE = 2;

async function loadPlaywright() {
  const alvo = process.env.PLAYWRIGHT_CORE;
  if (alvo) {
    const mod = await import(pathToFileURL(path.resolve(alvo, "index.js")).href);
    return mod.default ?? mod;
  }
  try {
    const mod = await import("playwright-core");
    return mod.default ?? mod;
  } catch {
    console.error(
      "capture-previews: playwright-core não encontrado. " +
        "Instale-o e rode com NODE_PATH apontando para o node_modules, " +
        "ou defina PLAYWRIGHT_CORE=/caminho/para/playwright-core.",
    );
    process.exit(1);
  }
}

async function main() {
  const { chromium } = await loadPlaywright();
  const executablePath = process.env.CHROME_PATH;
  const browser = await chromium.launch(executablePath ? { executablePath } : {});
  const context = await browser.newContext({ viewport: VIEWPORT, deviceScaleFactor: SCALE });
  const page = await context.newPage();

  await mkdir(OUT, { recursive: true });

  const shot = async (nome) => {
    const arquivo = path.join(OUT, `preview-${nome}.png`);
    // Deixa as animações de entrada terminarem antes de fotografar.
    await page.waitForTimeout(700);
    await page.screenshot({ path: arquivo });
    console.log(`✔ ${arquivo}`);
  };
  // Os itens do menu levam o contador junto ("Pastas 4"): casa pelo começo do nome.
  const nav = (label) =>
    page.locator(".sidebar").getByRole("button", { name: new RegExp(`^${label}`) }).first().click();

  await page.goto(BASE, { waitUntil: "networkidle" });
  await page.waitForSelector("text=Visão geral");
  // As capturas usam os dados fictícios do modo demonstração (para não expor
  // contas reais), mas o selo "Modo demonstração" sai da foto.
  await page.addStyleTag({
    content: ".sidebar .sidebar-card:last-child { display: none }",
  });
  await shot("dashboard");

  await nav("Pastas");
  await page.waitForSelector("text=Pastas");
  await shot("folders");

  await nav("Arquivos");
  await shot("files");

  await nav("Atividade");
  await shot("activity");

  await nav("Conflitos");
  await shot("conflicts");

  await nav("Ajustes");
  await shot("settings");

  const tema = page.getByRole("button", { name: /^Ativar tema (escuro|claro)$/ });
  if (await tema.count()) {
    await tema.first().click();
    await nav("Visão geral");
    await shot("dark");
    await tema.first().click(); // volta o tema para quem usar a máquina depois
  }

  await context.close();
  await browser.close();
}

main().catch((erro) => {
  console.error(erro);
  process.exit(1);
});
