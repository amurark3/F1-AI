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
 * Measured, not guessed: the slowest overview segment answers in ~3.3s when the
 * backend is already warm, so an earlier 3.5s budget left no margin at all and
 * timed out routinely in production. Ten seconds clears warm latency with room
 * to spare while still conceding a cold start rather than hanging on one.
 *
 * A slow render here does not make a reader wait. Every page that calls this is
 * on ISR, so a regeneration happens in the background while the previous render
 * is served; only an outright cache miss blocks, and that is the one case where
 * waiting beats rendering an empty page.
 */
const REQUEST_TIMEOUT_MS = 10_000;

/**
 * Budget for build-time generation, where no reader is waiting.
 *
 * Kept well under Next's own per-page static-generation limit (~60s). They are
 * not independent: if this budget can reach that limit, a slow backend stops
 * being a page that renders unseeded and becomes a build that fails outright,
 * which is the one outcome worse than missing data.
 */
const BUILD_TIMEOUT_MS = 25_000;

/** True while `next build` is generating pages rather than serving a request. */
const isBuildPhase = process.env.NEXT_PHASE === "phase-production-build";

/**
 * Status codes worth trying again.
 *
 * 429 is the one that matters: the backend sits on a free-tier host that
 * throttles bursts, and a prerender pass is exactly a burst. A throttled
 * response is not a failure, it is a request to wait — retrying turns it into
 * a seeded page instead of an empty one.
 */
const RETRYABLE_STATUSES = new Set([429, 502, 503, 504]);

/** Attempts per request, including the first. */
const MAX_ATTEMPTS = 3;

/** Backoff before attempt n, doubling each time. */
const backoffMs = (attempt: number): number => 400 * 2 ** (attempt - 1);

const sleep = (ms: number): Promise<void> => new Promise((resolve) => setTimeout(resolve, ms));

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
  // One deadline for the whole operation, retries and backoff included.
  // A per-attempt budget would multiply by the retry count and overrun whatever
  // the caller is racing — during a build, that is Next's own page limit.
  const budget = options.timeoutMs ?? (isBuildPhase ? BUILD_TIMEOUT_MS : REQUEST_TIMEOUT_MS);
  const deadline = Date.now() + budget;

  for (let attempt = 1; attempt <= MAX_ATTEMPTS; attempt += 1) {
    const remaining = deadline - Date.now();
    if (remaining <= 0) {
      logFailure(path, "budget exhausted");
      return null;
    }

    const outcome = await attemptFetch<T>(path, options, remaining);

    if (outcome.ok) return outcome.data;
    if (!outcome.retryable || attempt === MAX_ATTEMPTS) {
      logFailure(path, outcome.reason);
      return null;
    }

    // Only wait if the pause plus another attempt still fits.
    const pause = backoffMs(attempt);
    if (deadline - Date.now() <= pause) {
      logFailure(path, outcome.reason);
      return null;
    }
    await sleep(pause);
  }

  return null;
}

type Outcome<T> = { ok: true; data: T } | { ok: false; retryable: boolean; reason: string };

/** One attempt. Never throws; classifies the failure so the caller can retry. */
async function attemptFetch<T>(path: string, options: FetchOptions, budget: number): Promise<Outcome<T>> {
  const { revalidate, tags } = options;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), budget);

  try {
    const response = await fetch(`${SERVER_API_BASE}${path}`, {
      signal: controller.signal,
      next: revalidate === undefined ? undefined : { revalidate, tags: tags ? [...tags] : undefined },
      cache: revalidate === undefined ? "no-store" : undefined,
    });

    if (!response.ok) {
      return { ok: false, retryable: RETRYABLE_STATUSES.has(response.status), reason: `HTTP ${response.status}` };
    }

    return { ok: true, data: (await response.json()) as T };
  } catch (error: unknown) {
    // A timeout is worth one more go; the backend may have been waking up.
    return { ok: false, retryable: true, reason: describeError(error) };
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
