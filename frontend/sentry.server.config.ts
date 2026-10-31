// Server-side (Node.js runtime) Sentry, loaded by `register()` in instrumentation.ts.
import * as Sentry from "@sentry/nextjs";

import { SENTRY_OPTIONS } from "@/app/lib/errorTracking";

Sentry.init(SENTRY_OPTIONS);
