import { recheckServer } from "../lib/serverStatus";

/** Default timeout for `fetcherWithTimeout`, in milliseconds. */
const DEFAULT_TIMEOUT_MS = 35_000;

/**
 * Answers Render's proxy gives while the instance is restarting or booting. The
 * API itself never sends these, so seeing one means the server went away.
 */
const RESTARTING_STATUSES = new Set([502, 503, 504]);

/** Builds the error thrown for non-2xx responses. */
const httpError = (res: Response): Error => new Error(`Request failed: ${res.status} ${res.statusText}`);

/**
 * `fetch` that throws on non-2xx, and asks the readiness probe to look again
 * when the failure looks like a restart — a dropped connection, a timeout, or a
 * proxy error. A server that cold-restarts mid-visit then brings the warm-up
 * screen back instead of leaving every panel on an error.
 */
async function request(url: string, init?: RequestInit): Promise<Response> {
  const res = await fetch(url, init).catch((err: unknown) => {
    recheckServer();
    throw err;
  });
  if (RESTARTING_STATUSES.has(res.status)) recheckServer();
  if (!res.ok) throw httpError(res);
  return res;
}

/**
 * SWR-compatible fetch wrapper used by all data-fetching hooks.
 *
 * Throws an error for non-2xx HTTP responses so SWR can surface them
 * via the `error` return value rather than silently receiving bad JSON.
 *
 * The response body is trusted to match `T`; callers supply the shape via
 * the `useSWR<T>` generic at the call site.
 */
export const fetcher = async <T>(url: string): Promise<T> => {
  const res = await request(url);
  return (await res.json()) as T;
};

/**
 * Fetcher with a timeout. Used for potentially slow endpoints like race
 * detail that load data from FastF1 on first request.
 */
export const fetcherWithTimeout = async <T>(url: string, timeoutMs: number = DEFAULT_TIMEOUT_MS): Promise<T> => {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const res = await request(url, { signal: controller.signal });
    return (await res.json()) as T;
  } catch (err: unknown) {
    if (err instanceof DOMException && err.name === "AbortError") {
      throw new Error("Request timed out — the server may be loading data. Try again.");
    }
    throw err;
  } finally {
    clearTimeout(timer);
  }
};
