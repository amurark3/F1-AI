"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useMemo } from "react";

import { raceQuery, readRaceYear } from "@/app/ui/race-picker/raceUrl";

import { readRound } from "../debriefs/useDebriefUrl";

/** `?lap=`: a step number, or the final classification. */
export type UrlStep = number | "final";

export interface RewindUrl {
  year: number | null;
  /** The round the URL names; null when it names none or something that is no round. */
  round: number | null;
  /** The step the URL names; null when it names none or something that is no step. */
  step: UrlStep | null;
  select: (round: number) => void;
  /** Writes the step without a router navigation: dragging the scrubber must not navigate per step. */
  setStep: (round: number, step: UrlStep) => void;
}

/** What the server render shows: the default race and step, before the URL can be read. */
export const DEFAULT_REWIND_URL: RewindUrl = {
  year: null,
  round: null,
  step: null,
  select: () => undefined,
  setStep: () => undefined,
};

/** `?lap=` as "final" or a whole number from 0, else null. */
export function readStep(search: URLSearchParams): UrlStep | null {
  const value = search.get("lap");
  if (value === "final") return value;
  return value !== null && /^(0|[1-9]\d*)$/.test(value) ? Number(value) : null;
}

/** The round and step held in the URL, and ways to change them. */
export function useRewindUrl(currentYear: number): RewindUrl {
  const search = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const params = useMemo(() => new URLSearchParams(search.toString()), [search]);
  const year = readRaceYear(params, currentYear);
  const select = useCallback(
    (next: number) => router.replace(`${pathname}?${raceQuery(next, year)}`, { scroll: false }),
    [pathname, router, year],
  );
  const setStep = useCallback(
    (round: number, step: UrlStep) => {
      const query = raceQuery(round, year);
      query.set("lap", String(step));
      window.history.replaceState(null, "", `${pathname}?${query}`);
    },
    [pathname, year],
  );
  return useMemo(
    () => ({ year, round: readRound(params), step: readStep(params), select, setStep }),
    [params, select, setStep, year],
  );
}
