import * as Sentry from "@sentry/nextjs";

// Next.js calls this once per server runtime at startup.
export async function register() {
  if (process.env.NEXT_RUNTIME === "nodejs") {
    await import("./sentry.server.config");
  }
  if (process.env.NEXT_RUNTIME === "edge") {
    await import("./sentry.edge.config");
  }
}

// Errors thrown while rendering Server Components or handling route requests.
export const onRequestError = Sentry.captureRequestError;
