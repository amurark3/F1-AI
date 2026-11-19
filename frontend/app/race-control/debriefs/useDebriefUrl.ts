"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useMemo } from "react";

export interface DebriefUrl {
  /** The round the URL names; null when it names none or something that is no round. */
  round: number | null;
  select: (round: number) => void;
}

/** What the server render shows: the default round, before the URL can be read. */
export const DEFAULT_DEBRIEF_URL: DebriefUrl = { round: null, select: () => undefined };

/** `?round=` as a positive integer, else null. */
export function readRound(search: URLSearchParams): number | null {
  const value = search.get("round");
  return value !== null && /^[1-9]\d*$/.test(value) ? Number(value) : null;
}

/** The round held in the URL, and a way to change it without a scroll jump. */
export function useDebriefUrl(): DebriefUrl {
  const search = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const round = useMemo(() => readRound(new URLSearchParams(search.toString())), [search]);
  const select = useCallback(
    (next: number) => router.replace(`${pathname}?round=${next}`, { scroll: false }),
    [pathname, router],
  );
  return useMemo(() => ({ round, select }), [round, select]);
}
