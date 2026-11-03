import { defineConfig, devices } from "@playwright/test";

import { E2E_API_ORIGIN } from "./e2e/support/mockBackend";

/** A port of its own, so a `next dev` on 3000 is never mistaken for the e2e build. */
const PORT = 3100;
const BASE_URL = `http://127.0.0.1:${PORT}`;

/** A cold `next build` takes a minute or two; CI runners are slower. */
const SERVER_START_TIMEOUT_MS = 300_000;

const isCI = Boolean(process.env.CI);

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: isCI,
  // The backend is mocked, so a failure is a real failure: no retries.
  retries: 0,
  reporter: isCI ? "github" : "list",
  use: {
    baseURL: BASE_URL,
    trace: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: {
    // A production build, as Vercel serves it. NEXT_PUBLIC_API_URL is inlined
    // at build time, so the build itself must see the mock origin; a fresh
    // build every run keeps a stale `.next` from leaking a real backend in.
    command: `npm run build && npm run start -- --port ${PORT}`,
    url: BASE_URL,
    reuseExistingServer: false,
    timeout: SERVER_START_TIMEOUT_MS,
    env: {
      NEXT_PUBLIC_API_URL: E2E_API_ORIGIN,
      API_URL: E2E_API_ORIGIN,
      // Blank, not unset: Next does not let `.env.local` override a set variable.
      NEXT_PUBLIC_SENTRY_DSN: "",
    },
  },
});
