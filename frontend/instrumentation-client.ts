// Browser-side Sentry. Next.js loads this file before the app hydrates.
import * as Sentry from "@sentry/nextjs";

import { SENTRY_OPTIONS } from "@/app/lib/errorTracking";

Sentry.init(SENTRY_OPTIONS);

// Times client-side navigations, so a slow page change shows up in Traces.
export const onRouterTransitionStart = Sentry.captureRouterTransitionStart;
