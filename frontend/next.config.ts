import { withSentryConfig } from "@sentry/nextjs/config";

import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // The live timing page was folded into the command centre, which shows the
  // timing tower while a session is live. Old links land there instead.
  redirects: () =>
    Promise.resolve([
      { source: "/live", destination: "/race-control", permanent: false },
      { source: "/race-control/live", destination: "/race-control", permanent: false },
    ]),
};

export default withSentryConfig(nextConfig, {
  // Source maps are uploaded only when all three are set (Vercel project
  // settings); without them the build still succeeds, with minified stack traces.
  org: process.env.SENTRY_ORG,
  project: process.env.SENTRY_PROJECT,
  authToken: process.env.SENTRY_AUTH_TOKEN,
  widenClientFileUpload: true,
  // Only print upload logs in CI.
  silent: !process.env.CI,
  // The build plugin otherwise reports on every build to Sentry itself.
  telemetry: false,
  // Browser events go to Sentry through this app's own origin, so ad blockers
  // that block *.sentry.io do not drop them.
  tunnelRoute: "/monitoring",
});
