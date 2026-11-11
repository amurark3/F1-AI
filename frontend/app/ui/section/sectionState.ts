import type { ServerStatus } from "@/app/hooks/useServerStatus";

/**
 * Where one data section stands.
 *
 * - `pending`: nothing to show yet: the first answer is still out, or the
 *   server is restarting (not a fault).
 * - `ready`: data, fresh as of the last fetch.
 * - `stale`: data, but the latest refresh failed. The data stays on screen.
 * - `failed`: no data at all, and the server is up to say why.
 */
export type SectionStatus = "pending" | "ready" | "stale" | "failed";

/** What a section's frame needs: its status, why it is not fresh, and a way to try again. */
export interface SectionState {
  status: SectionStatus;
  /** Why the section failed or could not refresh; null while pending or ready. */
  reason: string | null;
  /** True while a fetch is out, a retry included. */
  refreshing: boolean;
  /** Fetch the section again now. */
  retry: () => void;
}

/** Shown while the backend restarts: the words P0c.7 (`feat/oracle-backend`) gave the Command Center. */
export const RESTARTING_REASON = "Waiting for the server to finish restarting.";

/** The browser's transport error, in words. */
export const UNREACHABLE_REASON = "Could not reach the server.";

/**
 * The one rule every section follows: data on screen stays on screen. A failed
 * refresh with data is `stale`, never `failed`, and a restart is never a fault.
 */
export function sectionStatus(hasData: boolean, failed: boolean, restarting: boolean): SectionStatus {
  if (hasData) return failed ? "stale" : "ready";
  return failed && !restarting ? "failed" : "pending";
}

/**
 * Whether the readiness probe says the backend is (re)starting: it has not
 * answered yet, or it answered "warming". A probe that gave up is not a
 * restart any more, so its sections say they failed.
 */
export function isRestarting(status: ServerStatus): boolean {
  return status === "unknown" || status === "warming";
}

/**
 * A fetch error, in words a reader can use.
 *
 * `fetch` rejects with a `TypeError` whose text differs by browser ("Failed to
 * fetch", "Load failed"), and tells a reader nothing; anything else came from
 * the fetcher or the backend and is passed on.
 */
export function describeFailure(error: Error, restarting: boolean): string {
  if (restarting) return RESTARTING_REASON;
  return error instanceof TypeError ? UNREACHABLE_REASON : error.message;
}

/**
 * The error a handled backend failure answers with: HTTP 200 and a non-empty
 * `error` string (`app/api/errors.client_error`). Null for a good payload.
 */
export function payloadError(body: unknown): string | null {
  if (typeof body !== "object" || body === null || Array.isArray(body)) return null;
  const { error } = body as { error?: unknown };
  return typeof error === "string" && error !== "" ? error : null;
}

/** A server-rendered seed worth showing: present and not an error payload. */
export function usableSeed<T>(seed: T | null | undefined): T | null {
  return seed != null && payloadError(seed) === null ? seed : null;
}
