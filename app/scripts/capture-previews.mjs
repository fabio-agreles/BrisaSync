#!/usr/bin/env node
// Captura as prévias usadas no README e no metainfo do Flatpak.
// Roda contra o build web em modo demonstração (dados simulados).

import { mkdir, copyFile } from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import { pathToFileURL } from "node:url";

const BASE = process.env.PREVIEW_URL ?? "http://localhost:4173";
const OUT = process.env.PREVIEW_DIR ?? path.join("docs", "previews");
const DOCS_IMAGES = path.resolve("..", "docs", "assets", "images");

// 1240x900 @2x = 2480x1800, o tamanho padrão do metainfo e documentação.
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
    console.error("capture-previews: playwright-core não encontrado.");
    process.exit(1);
  }
}

async function main() {
  const { chromium } = await loadPlaywright();
  const executablePath = process.env.CHROME_PATH;
  const browser = await chromium.launch({
    executablePath: executablePath || undefined,
    args: ["--no-sandbox", "--disable-setuid-sandbox"],
  });
  const context = await browser.newContext({
    viewport: VIEWPORT,
    deviceScaleFactor: SCALE,
  });
  const page = await context.newPage();

  await mkdir(OUT, { recursive: true });
  await mkdir(DOCS_IMAGES, { recursive: true });

  const shot = async (nome) => {
    const arquivo = path.join(OUT, `preview-${nome}.png`);
    await page.waitForTimeout(600);
    await page.screenshot({ path: arquivo });
    console.log(`✔ ${arquivo}`);
    return arquivo;
  };

  const nav = async (label) => {
    await page.locator(".sidebar").getByRole("button", { name: new RegExp(`^${label}`) }).first().click();
    await page.waitForTimeout(400);
  };

  await page.goto(BASE, { waitUntil: "networkidle" });
  await page.waitForSelector("text=Visão geral");

  // Ocultar selo "Modo demonstração" da foto
  await page.addStyleTag({
    content: ".sidebar .sidebar-card:last-child { display: none }",
  });

  // 1. Visão geral (tema claro)
  console.log("Capturando Visão geral...");
  await shot("dashboard");

  // 2. Pastas
  console.log("Capturando Pastas...");
  await nav("Pastas");
  await page.waitForSelector("text=Pastas");
  await shot("folders");

  // 3. Adicionar pasta (modal)
  console.log("Capturando Adicionar pasta...");
  const btnAdd = page.getByRole("button", { name: "Adicionar pasta" }).first();
  if (await btnAdd.count()) {
    await btnAdd.click();
    await page.waitForTimeout(500);
    await shot("add-folder");
    await page.keyboard.press("Escape");
    await page.waitForTimeout(300);
  }

  // 4. Arquivos
  console.log("Capturando Arquivos...");
  await nav("Arquivos");
  await page.waitForSelector("text=Arquivos");
  await shot("files");

  // 5. Atividade
  console.log("Capturando Atividade...");
  await nav("Atividade");
  await page.waitForSelector("text=Atividade");
  await shot("activity");

  // 6. Limpar atividade (modal)
  console.log("Capturando Limpar atividade...");
  const btnLimpar = page.getByRole("button", { name: "Limpar" }).first();
  if (await btnLimpar.count()) {
    await btnLimpar.click();
    await page.waitForTimeout(500);
    await shot("activity-clear");
    await page.keyboard.press("Escape");
    await page.waitForTimeout(300);
  }

  // 7. Conflitos
  console.log("Capturando Conflitos...");
  await nav("Conflitos");
  await page.waitForSelector("text=Conflitos");
  await shot("conflicts");

  // 8. Ajustes
  console.log("Capturando Ajustes...");
  await nav("Ajustes");
  await page.waitForSelector("text=Ajustes");
  await shot("settings");

  // 9. Ajustes Avançados
  console.log("Capturando Ajustes Avançados...");
  const adv = page.locator("text=Avançado · Google Drive");
  if (await adv.count()) {
    await adv.scrollIntoViewIfNeeded();
    await page.waitForTimeout(400);
    await shot("settings-advanced");
    await page.evaluate(() => window.scrollTo(0, 0));
  }

  // 10. Paleta de comandos (Ctrl K)
  console.log("Capturando Paleta de comandos...");
  await page.keyboard.press("Control+k");
  await page.waitForTimeout(500);
  await shot("palette");
  await page.keyboard.press("Escape");
  await page.waitForTimeout(300);

  // 11. Tema escuro
  console.log("Capturando Tema escuro...");
  const tema = page.getByRole("button", { name: /^Ativar tema (escuro|claro)$/ });
  if (await tema.count()) {
    await tema.first().click();
    await nav("Visão geral");
    await page.waitForTimeout(600);
    await shot("dark");

    // Também salvar cópia para flatpak.png
    await page.screenshot({ path: path.join(OUT, "flatpak.png") });
    console.log(`✔ ${path.join(OUT, "flatpak.png")}`);

    await tema.first().click(); // restaura tema
  }

  // Copiar imagens correspondentes para docs/assets/images/ do site
  console.log("Atualizando docs/assets/images/...");
  await copyFile(path.join(OUT, "preview-dashboard.png"), path.join(DOCS_IMAGES, "visao-geral.png"));
  await copyFile(path.join(OUT, "preview-folders.png"), path.join(DOCS_IMAGES, "pastas.png"));
  await copyFile(path.join(OUT, "preview-files.png"), path.join(DOCS_IMAGES, "arquivos.png"));
  await copyFile(path.join(OUT, "preview-settings.png"), path.join(DOCS_IMAGES, "ajustes.png"));
  await copyFile(path.join(OUT, "preview-dark.png"), path.join(DOCS_IMAGES, "tema-escuro.png"));

  // Capturar também as 5 telas em inglês para docs/assets/images/en/
  const DOCS_IMAGES_EN = path.join(DOCS_IMAGES, "en");
  await mkdir(DOCS_IMAGES_EN, { recursive: true });
  await nav("Ajustes");
  const btnEn = page.getByRole("button", { name: "English" }).first();
  if (await btnEn.count()) {
    await btnEn.click();
    await page.waitForTimeout(500);
    await page.screenshot({ path: path.join(DOCS_IMAGES_EN, "ajustes.png") });
    await nav("Overview");
    await page.waitForTimeout(500);
    await page.screenshot({ path: path.join(DOCS_IMAGES_EN, "visao-geral.png") });
    await nav("Folders");
    await page.waitForTimeout(500);
    await page.screenshot({ path: path.join(DOCS_IMAGES_EN, "pastas.png") });
    await nav("Files");
    await page.waitForTimeout(500);
    await page.screenshot({ path: path.join(DOCS_IMAGES_EN, "arquivos.png") });
    const temaEn = page.getByRole("button", { name: /^Switch to (dark|light) theme$/ });
    if (await temaEn.count()) {
      await temaEn.first().click();
      await nav("Overview");
      await page.waitForTimeout(600);
      await page.screenshot({ path: path.join(DOCS_IMAGES_EN, "tema-escuro.png") });
    }
    console.log("✔ Capturas em inglês salvas em docs/assets/images/en/");
  }
  await copyFile(path.join(OUT, "preview-dark.png"), path.join(DOCS_IMAGES, "tema-escuro.png"));
  console.log("✔ Imagens de docs/assets/images/ atualizadas!");

  await context.close();
  await browser.close();
}

main().catch((erro) => {
  console.error(erro);
  process.exit(1);
});
