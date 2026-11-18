"use client";

import { useMemo } from "react";

import { GrandPrixBoard, type GrandPrixBoardProps } from "./GrandPrixBoard";
import { resolveDefaultRace } from "./predictionHelpers";
import { useStartingGrid, useWeekendData } from "./useHubData";
import { useHubSections, useSeasonContext, resolveRound } from "./useHubShell";
import { usePredictionWorkspace } from "./usePredictionWorkspace";

import type { GrandPrixSeed } from "./hubSeed";
import type { HubUrl } from "./useHubUrlState";

/**
 * The hub's sections, each fed by its own request. Nothing here waits for a
 * whole page: the calendar and the entry list report their own state, and the
 * board shows each section's pending, failed or stale face in place.
 */
function useGrandPrixWorkspace(seed: GrandPrixSeed, url: HubUrl): GrandPrixBoardProps {
  const { year } = seed;
  const season = useSeasonContext(seed);
  const defaultRace = useMemo(() => resolveDefaultRace(season.schedule), [season.schedule]);
  const { effectiveRound, selectedRace } = resolveRound(season.schedule, url.round, defaultRace);
  const sections = useHubSections(url, selectedRace);

  const seeded = effectiveRound === seed.snapshotRound;
  const { grid, gridLoading } = useStartingGrid(year, effectiveRound, seeded ? seed.grid : null);
  const weekend = useWeekendData(
    year,
    effectiveRound,
    { sessions: seeded ? seed.sessions : null, strategy: seeded ? seed.strategy : null },
    sections.stintsWanted,
  );
  const { clearComputeError, ...prediction } = usePredictionWorkspace(seed, effectiveRound, selectedRace);

  return {
    ...prediction,
    year,
    activeTab: sections.activeTab,
    predictionView: sections.predictionView,
    onSelectTab: sections.onSelectTab,
    onSelectView: sections.onSelectView,
    schedule: season.schedule,
    schedulePending: season.schedulePending,
    scheduleError: season.scheduleFailed,
    selectedRound: effectiveRound,
    selectedRace: selectedRace ?? null,
    grid,
    gridLoading,
    sessions: weekend.sessions,
    sessionsLoading: weekend.sessionsLoading,
    strategy: weekend.strategy,
    strategyLoading: weekend.strategyLoading,
    drivers: season.drivers,
    driversError: season.driversFailed,
    onSelectRound: (round) => {
      // A new round starts over on Weekend; a tab carried across rounds was the inconsistency.
      url.update({ round, tab: null, view: null });
      clearComputeError();
    },
    onReloadSchedule: season.reloadSchedule,
    onReloadDrivers: season.reloadDrivers,
  };
}

export function GrandPrixView({ seed, url }: { seed: GrandPrixSeed; url: HubUrl }) {
  return <GrandPrixBoard {...useGrandPrixWorkspace(seed, url)} />;
}
