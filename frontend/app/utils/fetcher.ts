import { recheckServer } from "../lib/serverStatus";

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
async function request(url: string): Promise<Response> {
  const res = await fetch(url).catch((err: unknown) => {
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
