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
