"use client";

import { useState } from "react";

import { API_BASE } from "@/app/constants/api";
import { useSchedule } from "@/app/ui/race-picker/useSchedule";
import { useSection } from "@/app/ui/section/useSection";

import { defaultPredictionView, type HubTab } from "./hubNavigation";

import type { DriversResponse, GrandPrixSeed } from "./hubSeed";
import type { DriverStanding, RaceEvent } from "./predictionModel";
import type { HubUrl } from "./useHubUrlState";

const NO_DRIVERS: DriverStanding[] = [];
const DRIVERS_CONFIG = { revalidateOnFocus: false, dedupingInterval: 180000 };

/**
 * Resolve which round/race is in focus. A round the calendar does not hold —
 * a stale or hand-edited link — falls back to the default rather than
 * fetching for a race that does not exist.
 */
export function resolveRound(schedule: RaceEvent[], selectedRound: number | null, defaultRace: RaceEvent | null) {
  const selectedRace = schedule.find((r) => r.round === selectedRound) ?? defaultRace;
  return { effectiveRound: selectedRace?.round ?? null, selectedRace };
}

/**
 * The section and prediction view on screen: the URL's, else Weekend — every
 * round opens there, whatever stage its weekend has reached (user, 2026-11-18). Remembers that Stints was opened, so its slow load
 * starts only when someone asks for it and is not dropped on the next tab.
 */
export function useHubSections(url: HubUrl, race: RaceEvent | null) {
  const activeTab: HubTab = url.tab ?? "weekend";
  const [stintsWanted, setStintsWanted] = useState(activeTab === "stints");
  if (activeTab === "stints" && !stintsWanted) {
    setStintsWanted(true);
  }
  return {
    activeTab,
    predictionView: url.view ?? defaultPredictionView(race),
    stintsWanted,
    onSelectTab: (tab: HubTab) => url.update({ tab }),
    onSelectView: (view: NonNullable<HubUrl["view"]>) => url.update({ tab: "predictions", view }),
  };
}

/**
 * The season-wide inputs every tab needs: the calendar and the entry list.
 *
 * Both are per-season rather than per-round, so they sit apart from the
 * round-scoped fetches — selecting a different race must not refetch either.
 * Each owns its own state: a failing entry list shows a notice and retries in
 * place, and never takes the page down with it.
 */
export function useSeasonContext(seed: GrandPrixSeed) {
  const { year } = seed;
  const calendar = useSchedule(year, seed.schedule);
  const drivers = useSection<DriversResponse>(`${API_BASE}/api/race-control/drivers/${year}`, {
    seed: seed.drivers,
    config: DRIVERS_CONFIG,
  });

  return {
    schedule: calendar.races,
    schedulePending: calendar.pending,
    scheduleFailed: calendar.failed,
    reloadSchedule: calendar.retry,
    drivers: drivers.data?.drivers ?? NO_DRIVERS,
    driversFailed: drivers.status === "failed",
    reloadDrivers: drivers.retry,
  };
}
