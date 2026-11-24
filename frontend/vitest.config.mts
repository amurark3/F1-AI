import { fileURLToPath } from "node:url";

import { defineConfig } from "vitest/config";

/**
 * Source held to 100% coverage, per file, on every metric: all of `app/**`.
 *
 * The ratchet is complete (docs/plans/2026-11-redesign/PLAN.md, P9): every
 * file joined once its tests covered it fully, and nothing leaves. There is no
 * escape hatch: ESLint rejects coverage-ignore hint comments, so uncovered
 * code is either tested or deleted. Config files (`next.config.ts`,
 * `instrumentation*`, `sentry.*`) sit outside `app/` and so outside the gate.
 */
const COVERAGE_INCLUDE = ["app/**/*.{ts,tsx}"];

/** Not app code: tests, and declaration files, which compile to nothing. */
const COVERAGE_EXCLUDE = ["app/**/*.test.{ts,tsx}", "app/**/*.d.ts"];

/** Every metric must reach this in every included file. */
const FULL_COVERAGE = 100;

export default defineConfig({
  resolve: {
    // Mirrors tsconfig's `@/*` path, so tests import exactly as the app does.
    alias: { "@": fileURLToPath(new URL(".", import.meta.url)) },
  },
  test: {
    environment: "jsdom",
    // Unit and component tests sit next to their subject; e2e/ belongs to Playwright.
    include: ["app/**/*.test.{ts,tsx}", "test/**/*.test.{ts,tsx}"],
    setupFiles: ["./test/setup.ts"],
    restoreMocks: true,
    coverage: {
      provider: "v8",
      include: COVERAGE_INCLUDE,
      exclude: COVERAGE_EXCLUDE,
      // Lists every gated file, including the ones at 100%, as evidence. A
      // type-only module (`weekendTypes.ts`) compiles to nothing, so v8 counts
      // 0 of 0 everywhere: no threshold can fail on it, but the table would print
      // it as 0%. `skipEmpty` drops such files from the table; any file with
      // code still lists.
      reporter: [["text", { skipFull: false, skipEmpty: true }], "html"],
      thresholds: {
        perFile: true,
        statements: FULL_COVERAGE,
        branches: FULL_COVERAGE,
        functions: FULL_COVERAGE,
        lines: FULL_COVERAGE,
      },
    },
  },
});
