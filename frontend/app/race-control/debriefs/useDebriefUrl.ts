"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useMemo } from "react";

import { raceQuery, readRaceYear } from "@/app/ui/race-picker/raceUrl";

export interface DebriefUrl {
  year: number | null;
  /** The round the URL names; null when it names none or something that is no round. */
  round: number | null;
  select: (round: number) => void;
  /** Opens another season at its default round. */
  selectYear: (year: number) => void;
}

/** What the server render shows: the default round, before the URL can be read. */
export const DEFAULT_DEBRIEF_URL: DebriefUrl = {
  year: null,
  round: null,
  select: () => undefined,
  selectYear: () => undefined,
};

/** `?round=` as a positive integer, else null. */
export function readRound(search: URLSearchParams): number | null {
  const value = search.get("round");
  return value !== null && /^[1-9]\d*$/.test(value) ? Number(value) : null;
}

/** The round held in the URL, and a way to change it without a scroll jump. */
export function useDebriefUrl(currentYear: number): DebriefUrl {
  const search = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const params = useMemo(() => new URLSearchParams(search.toString()), [search]);
  const year = readRaceYear(params, currentYear);
  const round = readRound(params);
  const select = useCallback(
    (next: number) => router.replace(`${pathname}?${raceQuery(next, year)}`, { scroll: false }),
    [pathname, router, year],
  );
  const selectYear = useCallback(
    (next: number) => router.replace(`${pathname}?${raceQuery(null, next)}`, { scroll: false }),
    [pathname, router],
  );
  return useMemo(() => ({ year, round, select, selectYear }), [round, select, selectYear, year]);
}
