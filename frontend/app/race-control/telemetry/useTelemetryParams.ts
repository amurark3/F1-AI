"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useMemo } from "react";

import { FIRST_SEASON, TABS, type TabKey } from "./telemetryModel";

/**
 * What the page shows, held in the URL so a view can be shared and the Grand
 * Prix Hub can link straight to a round and tab.
 *
 * `round` and `session` stay null until chosen; the view then falls back to the
 * schedule's default round and the round's most relevant session.
 */
export interface TelemetryParams {
  tab: TabKey;
  year: number;
  round: number | null;
  session: string | null;
  a: string | null;
  b: string | null;
  lap: number | null;
}

const DRIVER_CODE = /^[A-Z]{3}$/;
const SESSION_CODES = new Set(["FP1", "FP2", "FP3", "SQ", "S", "Q", "R"]);

function positiveInt(value: string | null): number | null {
  if (value === null) return null;
  const parsed = Number.parseInt(value, 10);
  return Number.isInteger(parsed) && parsed > 0 ? parsed : null;
}

function driverCode(value: string | null): string | null {
  const code = (value ?? "").toUpperCase();
  return DRIVER_CODE.test(code) ? code : null;
}

/** Reads untrusted URL params into a valid selection, dropping anything malformed. */
export function readParams(search: URLSearchParams, currentYear: number): TelemetryParams {
  const tab = TABS.find((item) => item.key === search.get("tab"))?.key ?? "map";
  const year = positiveInt(search.get("year"));
  const session = (search.get("session") ?? "").toUpperCase();
  return {
    tab,
    year: year !== null && year >= FIRST_SEASON && year <= currentYear ? year : currentYear,
    round: positiveInt(search.get("round")),
    session: SESSION_CODES.has(session) ? session : null,
    a: driverCode(search.get("a")),
    b: driverCode(search.get("b")),
    lap: positiveInt(search.get("lap")),
  };
}

function toQuery(params: TelemetryParams): string {
  const query = new URLSearchParams();
  query.set("tab", params.tab);
  query.set("year", String(params.year));
  const optional: Array<[string, string | number | null]> = [
    ["round", params.round],
    ["session", params.session],
    ["a", params.a],
    ["b", params.b],
    ["lap", params.lap],
  ];
  for (const [key, value] of optional) {
    if (value !== null) query.set(key, String(value));
  }
  return query.toString();
}

export function useTelemetryParams(currentYear: number) {
  const search = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const params = useMemo(() => readParams(new URLSearchParams(search.toString()), currentYear), [search, currentYear]);

  const update = useCallback(
    (changes: Partial<TelemetryParams>) => {
      router.replace(`${pathname}?${toQuery({ ...params, ...changes })}`, { scroll: false });
    },
    [params, pathname, router],
  );

  return { params, update };
}
