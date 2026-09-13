import { API_BASE } from "@/app/constants/api";

/**
 * Server-side origin for the backend.
 *
 * Prefers `API_URL` so a deployment can point server renders at an internal
 * address (skipping the public edge) while the browser keeps using
 * `NEXT_PUBLIC_API_URL`. Falls back to the shared public base otherwise.
 */
function resolveServerBase(): string {
  const internal = process.env.API_URL?.trim();
  if (internal) return internal;
  return API_BASE;
}

const SERVER_API_BASE = resolveServerBase();

/**
 * How long a server render waits on the backend before giving up.
 *
 * Deliberately short. The backend runs on Render's free tier with a ~50s cold
 * start, and a server render that blocks that long would hold the whole
 * response hostage — strictly worse than the client-fetch behaviour it
 * replaces. On timeout we return null and the page renders its existing
 * loading state, letting SWR fetch from the browser exactly as before.
 */
const REQUEST_TIMEOUT_MS = 3_500;

/**
 * Longer budget for build-time generation, where there is no user waiting and
 * paying the cold start once warms the backend for every remaining page.
 */
const BUILD_TIMEOUT_MS = 60_000;

/** True while `next build` is generating pages rather than serving a request. */
const isBuildPhase = process.env.NEXT_PHASE === "phase-production-build";

export interface FetchOptions {
  /** Seconds before Next's data cache refetches. Omit for `no-store`. */
  revalidate?: number;
  /** Cache tags, for targeted revalidation. */
  tags?: readonly string[];
  /** Overrides the default timeout. */
  timeoutMs?: number;
}

/**
 * Fetches JSON from the backend during a server render.
 *
 * Never throws and never rejects: every failure path — non-2xx, timeout,
 * unreachable host, malformed body — resolves to null. Callers treat null as
 * "no server data available" and hand the fetch back to the client, so a cold
 * or broken backend degrades to today's behaviour instead of an error page.
 */
export async function fetchFromBackend<T>(path: string, options: FetchOptions = {}): Promise<T | null> {
  const { revalidate, tags, timeoutMs } = options;
  const budget = timeoutMs ?? (isBuildPhase ? BUILD_TIMEOUT_MS : REQUEST_TIMEOUT_MS);

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), budget);

  try {
    const response = await fetch(`${SERVER_API_BASE}${path}`, {
      signal: controller.signal,
      next: revalidate === undefined ? undefined : { revalidate, tags: tags ? [...tags] : undefined },
      cache: revalidate === undefined ? "no-store" : undefined,
    });

    if (!response.ok) {
      logFailure(path, `HTTP ${response.status}`);
      return null;
    }

    return (await response.json()) as T;
  } catch (error: unknown) {
    logFailure(path, describeError(error));
    return null;
  } finally {
    clearTimeout(timer);
  }
}

/** Renders an unknown thrown value as a short diagnostic string. */
function describeError(error: unknown): string {
  if (error instanceof DOMException && error.name === "AbortError") return "timed out";
  if (error instanceof Error) return error.message;
  return "unknown error";
}

/**
 * Records a degraded server fetch.
 *
 * Server-side only, so the detail never reaches a browser; it is the one signal
 * that distinguishes "backend is cold" from "page has no data to show".
 */
function logFailure(path: string, reason: string): void {
  console.warn(`[ssr] ${path} unavailable (${reason}) — falling back to client fetch`);
}
