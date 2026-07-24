/** Default timeout for `fetcherWithTimeout`, in milliseconds. */
const DEFAULT_TIMEOUT_MS = 35_000;

/** Builds the error thrown for non-2xx responses. */
const httpError = (res: Response): Error =>
  new Error(`Request failed: ${res.status} ${res.statusText}`);

/**
 * SWR-compatible fetch wrapper used by all data-fetching hooks.
 *
 * Throws an error for non-2xx HTTP responses so SWR can surface them
 * via the `error` return value rather than silently receiving bad JSON.
 *
 * The response body is trusted to match `T`; callers supply the shape via
 * the `useSWR<T>` generic at the call site.
 */
export const fetcher = async <T,>(url: string): Promise<T> => {
  const res = await fetch(url);
  if (!res.ok) throw httpError(res);
  return (await res.json()) as T;
};

/**
 * Fetcher with a timeout. Used for potentially slow endpoints like race
 * detail that load data from FastF1 on first request.
 */
export const fetcherWithTimeout = async <T,>(
  url: string,
  timeoutMs: number = DEFAULT_TIMEOUT_MS,
): Promise<T> => {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const res = await fetch(url, { signal: controller.signal });
    if (!res.ok) throw httpError(res);
    return (await res.json()) as T;
  } catch (err: unknown) {
    if (err instanceof DOMException && err.name === "AbortError") {
      throw new Error(
        "Request timed out — the server may be loading data. Try again.",
      );
    }
    throw err;
  } finally {
    clearTimeout(timer);
  }
};
