// @vitest-environment node
// Reads globals.css from disk; jsdom would give import.meta.url a non-file scheme.
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import { f1, font, rc } from "./tokens";

const GLOBALS_CSS = readFileSync(fileURLToPath(new URL("../globals.css", import.meta.url)), "utf8");

/** The custom properties declared directly inside the first block that opens with `opener`. */
function declarations(opener: string): Map<string, string> {
  const css = GLOBALS_CSS.replaceAll(/\/\*[\s\S]*?\*\//g, "");
  const start = css.indexOf(`${opener} {`);
  if (start === -1) throw new Error(`globals.css has no "${opener}" block`);
  const body = css.slice(css.indexOf("{", start) + 1, css.indexOf("}", start));
  const entries = [...body.matchAll(/(--[\w-]+)\s*:\s*([^;]+);/g)].map(
    ([, name, value]) => [name, value.trim()] as const,
  );
  return new Map(entries);
}

/** `redText` → `red-text`, `ink2` → `ink-2`: the CSS spelling of a token key. */
function kebab(key: string): string {
  return key
    .replaceAll(/([A-Z])/g, "-$1")
    .replaceAll(/(\d+)/g, "-$1")
    .toLowerCase();
}

const root = declarations(":root");
const theme = declarations("@theme inline");

function rootValue(name: string): string | undefined {
  return root.get(name)?.toLowerCase();
}

describe("tokens.ts mirrors globals.css", () => {
  it.each(Object.entries(rc))("rc.%s matches --rc-* in :root", (key, value) => {
    expect(rootValue(`--rc-${kebab(key)}`)).toBe(value.toLowerCase());
  });

  it("has a token for every --rc-* custom property in :root", () => {
    const cssNames = [...root.keys()].filter((name) => name.startsWith("--rc-"));
    const tokenNames = Object.keys(rc).map((key) => `--rc-${kebab(key)}`);
    expect(tokenNames.sort()).toEqual(cssNames.sort());
  });

  it("exposes every rc token to Tailwind as --color-rc-*", () => {
    const themed = [...theme.entries()].filter(([name]) => name.startsWith("--color-rc-"));
    const expected = Object.keys(rc).map((key) => [`--color-rc-${kebab(key)}`, `var(--rc-${kebab(key)})`]);
    expect(themed.sort()).toEqual(expected.sort());
  });

  it.each(Object.entries(f1))("f1.%s matches --f1-* in :root", (key, value) => {
    expect(rootValue(`--f1-${kebab(key)}`)).toBe(value.toLowerCase());
  });

  it.each(Object.entries(font))("font.%s matches --font-* in @theme inline", (key, value) => {
    expect(theme.get(`--font-${key}`)).toBe(value);
  });
});

describe("token values", () => {
  it("are six-digit hex colours, so SVG and Recharts can take them as-is", () => {
    for (const value of [...Object.values(rc), ...Object.values(f1)]) {
      expect(value).toMatch(/^#[\da-f]{6}$/i);
    }
  });

  it("keep the gain green apart from the DRS green", () => {
    expect(rc.gain).not.toBe(f1.drs);
  });

  it("draw the display face from the Barlow Condensed font that next/font loads", () => {
    expect(font.display).toMatch(/^var\(--font-barlow\)/);
  });
});

describe("the globals.css parser", () => {
  it("fails loudly on a block the file does not have", () => {
    expect(() => declarations("@theme static")).toThrow('globals.css has no "@theme static" block');
  });
});

describe("focus ring", () => {
  it("is one red-text outline in the base layer, for every keyboard-reachable control", () => {
    const css = GLOBALS_CSS.replaceAll(/\/\*[\s\S]*?\*\//g, "");
    const base = css.slice(css.indexOf("@layer base {"));
    const rule = /:where\(([^)]*)\):focus-visible\s*\{([^}]*)\}/.exec(base);

    expect(rule?.[1].split(",").map((part) => part.trim())).toEqual(["a", "button", "summary", "select", "[tabindex]"]);
    expect(rule?.[2]).toMatch(/outline:\s*2px solid var\(--rc-red-text\);/);
    expect(rule?.[2]).toMatch(/outline-offset:\s*2px;/);
  });
});
