const DEFAULT_API_BASE = "http://localhost:8000";

/**
 * Resolves the backend origin.
 *
 * A blank `NEXT_PUBLIC_API_URL` (set but empty at build time) falls back to the
 * local default rather than producing requests against a relative empty origin.
 */
function resolveApiBase(): string {
  const configured = process.env.NEXT_PUBLIC_API_URL?.trim();
  if (configured) return configured;
  return DEFAULT_API_BASE;
}

export const API_BASE = resolveApiBase();
