/**
 * SWR-compatible fetch wrapper used by all data-fetching hooks.
 *
 * Throws an error for non-2xx HTTP responses so SWR can surface them
 * via the `error` return value rather than silently receiving bad JSON.
 */
export const fetcher = (url: string) =>
  fetch(url).then((res) => {
    if (!res.ok) {
      throw new Error(`Request failed: ${res.status} ${res.statusText}`);
    }
    return res.json();
  });

/**
 * Fetcher with a timeout (default 35s). Used for potentially slow endpoints
 * like race detail that load data from FastF1 on first request.
 */
export const fetcherWithTimeout = (url: string, timeoutMs = 35000) => {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  return fetch(url, { signal: controller.signal })
    .then((res) => {
      clearTimeout(timer);
      if (!res.ok) throw new Error(`Request failed: ${res.status} ${res.statusText}`);
      return res.json();
    })
    .catch((err) => {
      clearTimeout(timer);
      if (err.name === 'AbortError') {
        throw new Error('Request timed out — the server may be loading data. Try again.');
      }
      throw err;
    });
};
