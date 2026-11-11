"use client";

import { useCallback, useEffect, useRef } from "react";
import useSWR, { type SWRConfiguration } from "swr";

import { useServerStatus } from "@/app/hooks/useServerStatus";
import { seededWith } from "@/app/lib/swrFallback";
import { fetcher } from "@/app/utils/fetcher";

import {
  describeFailure,
  isRestarting,
  payloadError,
  sectionStatus,
  usableSeed,
  type SectionState,
} from "./sectionState";

export interface UseSectionOptions<T> {
  /** The server render's payload, if it had one. One that carries an `error` is dropped. */
  seed?: T | null;
  /** SWR options for this section's cache entry, such as `dedupingInterval`. */
  config?: SWRConfiguration<T, Error>;
}

export interface SectionResult<T> extends SectionState {
  /** The last good payload: set when `ready` or `stale`, never an error payload. */
  data: T | undefined;
}

/**
 * The fetcher, plus the backend's handled failures: an HTTP 200 whose body
 * carries an `error` throws, so SWR keeps the last good data and reports the
 * failure instead of caching the apology as data.
 */
async function fetchSection<T>(url: string): Promise<T> {
  const body = await fetcher<T>(url);
  const failure = payloadError(body);
  if (failure !== null) throw new Error(failure);
  return body;
}

/**
 * Fetches one section of a page and says where it stands (see `SectionStatus`).
 *
 * SWR owns the request; a server render only seeds it, so a page with no seed
 * still fills itself in the browser. Data on screen stays on screen: a failed
 * refresh is `stale`, never `failed`. While the readiness probe says the
 * backend is restarting, a failure with nothing to show stays `pending`, and
 * the section fetches again the moment the probe says ready, rather than
 * waiting out SWR's retry backoff.
 */
export function useSection<T>(url: string, { seed, config }: UseSectionOptions<T> = {}): SectionResult<T> {
  const restarting = isRestarting(useServerStatus().status);
  const { data, error, isValidating, mutate } = useSWR<T, Error>(url, fetchSection, {
    ...config,
    ...seededWith(usableSeed(seed)),
  });

  // Another hook on the same key may have cached a handled failure as data.
  const payloadFailure = data === undefined ? null : payloadError(data);
  const usable = payloadFailure === null ? data : undefined;
  const failure = error ? describeFailure(error, restarting) : payloadFailure;
  const status = sectionStatus(usable !== undefined, failure !== null, restarting);

  const retry = useCallback(() => {
    void mutate();
  }, [mutate]);

  const wasRestarting = useRef(restarting);
  useEffect(() => {
    const recovered = wasRestarting.current && !restarting;
    wasRestarting.current = restarting;
    if (recovered && failure !== null) retry();
  }, [restarting, failure, retry]);

  return {
    status,
    data: usable,
    reason: status === "stale" || status === "failed" ? failure : null,
    refreshing: isValidating,
    retry,
  };
}
