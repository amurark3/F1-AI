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
  // P3.4: the root layout, its faces, the 404 and the last-resort error page.
  "app/fonts.ts",
  "app/global-error.tsx",
  "app/layout.tsx",
  "app/not-found.tsx",
  // P3.3: the static homepage.
  "app/page.tsx",
  "app/home/content.ts",
  "app/home/HomeHero.tsx",
  "app/home/HomeSections.tsx",
  "app/home/motifs.tsx",
  "app/lib/clinch.ts",
  "app/lib/standingsFreshness.ts",
  "app/ui/**",
  "app/race-control/components/BaselineStrategyPanel.tsx",
  "app/race-control/components/CommandCenterPanels.tsx",
  "app/race-control/components/Disclosure.tsx",
  "app/race-control/components/RaceControlPrimitives.tsx",
  "app/race-control/components/Tabs.tsx",
  // P0b.7: the "vs grid" helper.
  "app/race-control/grand-prix/gridDelta.ts",
  // P4.3b2: the hub's frame (header, URL-driven sections, season inputs) and
  // the Results tab.
  "app/race-control/grand-prix/HubHeader.tsx",
  "app/race-control/grand-prix/hubNavigation.ts",
  "app/race-control/grand-prix/ResultsSidePanels.tsx",
  "app/race-control/grand-prix/resultsModel.ts",
  "app/race-control/grand-prix/ResultsTab.tsx",
  "app/race-control/grand-prix/ResultsTable.tsx",
  // P4.3b3: the Sessions and Grid tabs.
  "app/race-control/grand-prix/GridPenalties.tsx",
  "app/race-control/grand-prix/gridHelpers.ts",
  "app/race-control/grand-prix/GridTab.tsx",
  "app/race-control/grand-prix/qualifyingModel.ts",
  "app/race-control/grand-prix/QualifyingSidePanels.tsx",
  "app/race-control/grand-prix/SessionsTab.tsx",
  "app/race-control/grand-prix/SessionTables.tsx",
  "app/race-control/grand-prix/StartingGrid.tsx",
  "app/race-control/grand-prix/StateTag.tsx",
  "app/race-control/grand-prix/useHubShell.ts",
  // P4.3b4: the Weekend and Stints tabs, and the tyre colours they read.
  "app/race-control/grand-prix/StintChart.tsx",
  "app/race-control/grand-prix/StintOverlay.tsx",
  "app/race-control/grand-prix/strategyModel.ts",
  "app/race-control/grand-prix/tyreCompounds.ts",
  "app/race-control/grand-prix/WeekendFacts.tsx",
  "app/race-control/grand-prix/WeekendGlance.tsx",
  "app/race-control/grand-prix/WeekendTabHero.tsx",
  "app/race-control/grand-prix/WeekendPanels.tsx",
  "app/race-control/grand-prix/WeekendSchedule.tsx",
  "app/race-control/grand-prix/weekendTabModel.ts",
  // P2.3a: the profiles files the redesign keeps. FinishChip, ProfileCharts,
  // PowerUnitCards and ProfileStates stay off: P5.4 / P6.3 rebuild or remove them.
  // P5.4a/b: the Teams index, the Team page and the rest of constructors/. The [driver] page
  // joins as P5.4c rebuilds it; the profiles files the Team page needs are listed one by one
  // until then (finishes, MissingProfile, the power-unit card).
  "app/race-control/constructors/**",
  "app/race-control/profiles/carAllocationsModel.ts",
  "app/race-control/profiles/CarAllocations.tsx",
  "app/race-control/profiles/finishes.ts",
  "app/race-control/profiles/MissingProfile.tsx",
  "app/race-control/profiles/EntityLinks.tsx",
  "app/race-control/profiles/profilesModel.ts",
  "app/race-control/weekend/**",
  // P4.4a: the Telemetry Lab toolbar and the speed map. P4.4b adds the head-to-head cards. The
  // tyre-wear files stay off: P4.4c rebuilds them.
  "app/race-control/telemetry/AnalysisNotice.tsx",
  "app/race-control/telemetry/AnalysisPickers.tsx",
  "app/race-control/telemetry/AnalysisToolbar.tsx",
  "app/race-control/telemetry/degradationInsights.ts",
  "app/race-control/telemetry/degradationModel.ts",
  "app/race-control/telemetry/DegradationCharts.tsx",
  "app/race-control/telemetry/HeadToHeadCard.tsx",
  "app/race-control/telemetry/HeadToHeadCards.tsx",
  "app/race-control/telemetry/HeadToHeadControls.tsx",
  "app/race-control/telemetry/HeadToHeadPanel.tsx",
  "app/race-control/telemetry/headToHeadInsights.ts",
  "app/race-control/telemetry/headToHeadModel.ts",
  "app/race-control/telemetry/qualifyingSegments.ts",
  "app/race-control/telemetry/telemetryModel.ts",
  "app/race-control/telemetry/TelemetryView.tsx",
  "app/race-control/telemetry/TelemetryTraces.tsx",
  "app/race-control/telemetry/TrackMap.tsx",
  "app/race-control/telemetry/TrackMapControls.tsx",
  "app/race-control/telemetry/trackMapGeometry.ts",
  "app/race-control/telemetry/TrackMapPanel.tsx",
  "app/race-control/telemetry/trackMapSelection.ts",
  "app/race-control/telemetry/TyreDegPanel.tsx",
  "app/race-control/telemetry/useAnalysisData.ts",
  "app/race-control/telemetry/useTelemetryParams.ts",
  // P4.3b5: the Predictions tab (Order and Review rebuilt, the rest of the tab's files with
  // them) and the hub's last files, so every file in grand-prix/ is now gated.
  "app/race-control/grand-prix/CallChart.tsx",
  "app/race-control/grand-prix/computeRun.ts",
  "app/race-control/grand-prix/GrandPrixBoard.tsx",
  "app/race-control/grand-prix/GrandPrixHub.tsx",
  "app/race-control/grand-prix/GrandPrixView.tsx",
  "app/race-control/grand-prix/gridModel.ts",
  "app/race-control/grand-prix/hubSeed.ts",
  "app/race-control/grand-prix/OrderPanels.tsx",
  "app/race-control/grand-prix/OrderTable.tsx",
  "app/race-control/grand-prix/page.tsx",
  "app/race-control/grand-prix/predictionHelpers.ts",
  "app/race-control/grand-prix/predictionModel.ts",
  "app/race-control/grand-prix/PredictionPhaseTabs.tsx",
  "app/race-control/grand-prix/PredictionResultsReview.tsx",
  "app/race-control/grand-prix/PredictionSection.tsx",
  "app/race-control/grand-prix/predictionState.ts",
  "app/race-control/grand-prix/RetirementCalls.tsx",
  "app/race-control/grand-prix/reviewModel.ts",
  "app/race-control/grand-prix/RiskModelPanels.tsx",
  "app/race-control/grand-prix/sessionsModel.ts",
  "app/race-control/grand-prix/useHubData.ts",
  "app/race-control/grand-prix/useHubUrlState.ts",
  "app/race-control/grand-prix/usePredictionWorkspace.ts",
  // P5.2: the Standings page (route kept at /race-control/teams) and the old /standings redirect.
  "app/race-control/teams/**",
  "app/standings/page.tsx",
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
