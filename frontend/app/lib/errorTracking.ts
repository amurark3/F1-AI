/**
 * Sentry options shared by the browser, Node and edge runtimes — the frontend
 * counterpart of the backend's `app/error_tracking.py`.
 *
 * Off by default: without `NEXT_PUBLIC_SENTRY_DSN` the SDK is disabled, so
 * local runs and CI builds send nothing anywhere. The DSN is public by design
 * (every browser that loads the app sees it), hence the `NEXT_PUBLIC_` prefix;
 * it is still read from the environment so each deployment chooses its project.
 */

import type * as Sentry from "@sentry/nextjs";

const DEFAULT_TRACES_SAMPLE_RATE = 0.1;

const dsn = process.env.NEXT_PUBLIC_SENTRY_DSN?.trim();

export const SENTRY_OPTIONS = {
  dsn,
  enabled: Boolean(dsn),
  // Vercel exposes "production" / "preview" / "development"; elsewhere fall
  // back to Node's own notion of the build.
  environment: process.env.NEXT_PUBLIC_VERCEL_ENV ?? process.env.NODE_ENV,
  tracesSampleRate: DEFAULT_TRACES_SAMPLE_RATE,
  // The JavaScript SDK collects user data by default — the reverse of the
  // Python SDK the backend uses — so every category that could carry something
  // personal is switched off. HTTP bodies matter most: they would include
  // whatever a user types to the AI Engineer.
  dataCollection: {
    userInfo: false,
    cookies: false,
    httpBodies: [],
  },
} satisfies Parameters<typeof Sentry.init>[0];
