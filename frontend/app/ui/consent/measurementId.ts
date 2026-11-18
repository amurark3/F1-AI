/** GA4 measurement IDs look like `G-AB12CD34EF`. */
const MEASUREMENT_ID = /^G-[A-Z0-9]{4,20}$/;

/**
 * The GA4 measurement ID, or null when it is unset or not shaped like one.
 * It is pasted into an inline script, so nothing else gets through.
 */
export function measurementId(raw: string | undefined): string | null {
  return raw !== undefined && MEASUREMENT_ID.test(raw) ? raw : null;
}

/**
 * Google Analytics and its banner exist only when this is set at build time.
 * Kept apart from the consent store so the server-rendered root layout can read
 * it without pulling in client-only React hooks.
 */
export const GA_ID = measurementId(process.env.NEXT_PUBLIC_GA_ID);
