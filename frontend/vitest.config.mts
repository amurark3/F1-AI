import { fileURLToPath } from "node:url";

import { defineConfig } from "vitest/config";

/**
 * Files held to 100% coverage, per file, on every metric.
 *
 * The list is a ratchet: a folder joins once its tests cover it fully, and
 * nothing leaves (docs/plans/2026-11-redesign/PLAN.md, P1.8). There is no
 * escape hatch: ESLint rejects coverage-ignore hint comments, so uncovered
 * code is either tested or deleted.
 */
const COVERAGE_INCLUDE = [
  "app/lib/standingsFreshness.ts",
  "app/ui/**",
  "app/race-control/components/CommandCenterPanels.tsx",
  "app/race-control/components/Disclosure.tsx",
  "app/race-control/components/RaceControlPrimitives.tsx",
  "app/race-control/components/RefreshButton.tsx",
  "app/race-control/components/Tabs.tsx",
  "app/race-control/weekend/**",
];

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
