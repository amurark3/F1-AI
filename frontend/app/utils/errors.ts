/**
 * Narrows an unknown thrown value to a human-readable message.
 *
 * `catch` bindings and SWR `error` values are untrusted, so they are narrowed
 * here rather than being interpolated directly into UI strings.
 */
export function getErrorMessage(error: unknown, fallback = "Something went wrong."): string {
  if (error instanceof Error) return error.message;
  if (typeof error === "string" && error.trim()) return error;
  return fallback;
}

/**
 * Returns the first value that is present and not blank.
 *
 * Used where a blank string must fall through to the next candidate — `??`
 * would stop at `""` and surface an empty message to the user.
 */
export function firstNonBlank(...values: Array<string | null | undefined>): string | undefined {
  for (const value of values) {
    const trimmed = value?.trim();
    if (trimmed) return trimmed;
  }
  return undefined;
}
