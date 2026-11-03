/**
 * Renders the two raster brand images that Next.js serves from `app/`:
 *
 * - `app/apple-icon.png`: the B1 mark (`app/icon.svg`) at 180 × 180, full
 *   bleed. iOS rounds the corners itself and turns transparency black, so the
 *   tile colour fills the whole square.
 * - `app/opengraph-image.png`: the 1200 × 630 link preview, the mark and the
 *   F1·AI wordmark on the hero colour.
 *
 * Run it from `frontend/` after changing the mark, the tokens or this file,
 * and commit the two PNGs:
 *
 *   node scripts/render-brand-images.mjs
 *
 * It needs Node ≥ 22.18 (it imports `app/ui/tokens.ts` directly), Playwright's
 * Chromium (`npx playwright install chromium`, as for `npm run e2e`) and
 * network access to Google Fonts, which serves the wordmark's Barlow Condensed
 * and the tagline's Geist Mono.
 */
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { chromium } from "@playwright/test";

import { f1, rc } from "../app/ui/tokens.ts";

const APP_DIR = new URL("../app/", import.meta.url);
const ICON_SVG = readFileSync(new URL("icon.svg", APP_DIR), "utf8");

const APPLE_ICON_SIZE = { width: 180, height: 180 };
const OG_SIZE = { width: 1200, height: 630 };
const OG_TAGLINE = "Your AI race engineer";

/** The faces the preview sets, as `document.fonts.load` takes them. */
const OG_FONTS = ['800 100px "Barlow Condensed"', '600 24px "Geist Mono"'];
const GOOGLE_FONTS_CSS =
  "https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@800&family=Geist+Mono:wght@600&display=block";

const APPLE_ICON_HTML = `<!DOCTYPE html>
<style>
  html, body { margin: 0; background: ${rc.hero}; }
  svg { display: block; width: ${APPLE_ICON_SIZE.width}px; height: ${APPLE_ICON_SIZE.height}px; }
</style>
${ICON_SVG}`;

/** The header lockup (`app/ui/BrandLockup.tsx`) at preview scale, over a tagline and a red rule. */
const OG_HTML = `<!DOCTYPE html>
<link rel="stylesheet" href="${GOOGLE_FONTS_CSS}" />
<style>
  html, body { margin: 0; height: 100%; }
  body {
    display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 40px;
    background: ${rc.hero}; box-shadow: inset 0 -10px 0 ${f1.red};
  }
  .lockup { display: flex; align-items: center; gap: 12px; }
  .lockup svg { width: 220px; height: 220px; }
  .wordmark {
    display: flex; align-items: center;
    font: 800 232px/1 "Barlow Condensed"; letter-spacing: 0.01em; color: ${rc.ink};
  }
  .wordmark i { width: 0.23em; height: 0.23em; margin: 0 0.115em; background: ${f1.red}; transform: translateY(0.04em); }
  .tagline {
    font: 600 24px/1 "Geist Mono"; letter-spacing: 0.22em; text-transform: uppercase; color: ${rc.ink3};
  }
</style>
<div class="lockup">${ICON_SVG}<div class="wordmark">F1<i></i>AI</div></div>
<p class="tagline">${OG_TAGLINE}</p>`;

/** Fails loudly when a web font did not arrive, rather than shipping a fallback face. */
async function assertFontsLoaded(page) {
  const missing = await page.evaluate(async (fonts) => {
    const loaded = await Promise.all(fonts.map((font) => document.fonts.load(font)));
    return fonts.filter((_, index) => loaded[index].length === 0);
  }, OG_FONTS);
  if (missing.length > 0) {
    throw new Error(`Fonts did not load from Google Fonts: ${missing.join(", ")}`);
  }
}

async function renderPng(browser, { html, size, file, needsFonts }) {
  const page = await browser.newPage({ viewport: size, deviceScaleFactor: 1 });
  try {
    await page.setContent(html, { waitUntil: "networkidle" });
    if (needsFonts) await assertFontsLoaded(page);
    const path = fileURLToPath(new URL(file, APP_DIR));
    await page.screenshot({ path });
    console.warn(`wrote ${path} (${size.width} × ${size.height})`);
  } finally {
    await page.close();
  }
}

const browser = await chromium.launch();
try {
  await renderPng(browser, {
    html: APPLE_ICON_HTML,
    size: APPLE_ICON_SIZE,
    file: "apple-icon.png",
    needsFonts: false,
  });
  await renderPng(browser, { html: OG_HTML, size: OG_SIZE, file: "opengraph-image.png", needsFonts: true });
} catch (error) {
  console.error("render-brand-images failed:", error instanceof Error ? error.message : error);
  process.exitCode = 1;
} finally {
  await browser.close();
}
