"use client";

import { API_BASE } from "@/app/constants/api";
import { Section } from "@/app/ui/section/Section";
import { useSection } from "@/app/ui/section/useSection";

import { Panel } from "../components/RaceControlPrimitives";
import { ChampionshipStakes } from "../weekend/ChampionshipStakes";
import { CircuitHistoryPanel } from "../weekend/CircuitHistoryPanel";

import { WeekendFacts } from "./WeekendFacts";
import { WeekendGlance } from "./WeekendGlance";
import { WeekendSchedule } from "./WeekendSchedule";
import { WeekendHero } from "./WeekendTabHero";

import type { RaceEvent } from "./predictionModel";
import type { RoundCircuit } from "./weekendTabModel";
import type { OverviewShell } from "../components/CommandCenterPanels";

const SWR_OPTIONS = { revalidateOnFocus: false, dedupingInterval: 120_000 };

/**
 * The title fight, when this is the round it is being fought over. The shell
 * serves the current standings for the next race, so on any other round it
 * would describe a different weekend and is left out.
 */
function WeekendStakes({ year, race }: { year: number; race: RaceEvent }) {
  const shell = useSection<OverviewShell>(`${API_BASE}/api/race-control/overview/${year}/shell`, {
    config: SWR_OPTIONS,
  });
  if (shell.data?.race?.round !== race.round || !shell.data.stakes) return null;
  return <ChampionshipStakes stakes={shell.data.stakes} venue={race.location.split(",")[0]} />;
}

function useRoundCircuit(year: number, round: number) {
  return useSection<RoundCircuit>(`${API_BASE}/api/race-control/circuit/${year}/${round}`, { config: SWR_OPTIONS });
}

/**
 * The Weekend tab's head, drawn above the tabs in place of the one-line race
 * header (`grand-prix.html`): the hero, then the circuit's four figures.
 */
export function WeekendTop({ year, race, totalRounds }: { year: number; race: RaceEvent; totalRounds: number }) {
  const circuit = useRoundCircuit(year, race.round);
  return (
    <div className="space-y-4">
      <WeekendHero year={year} race={race} circuit={circuit} totalRounds={totalRounds} />
      <WeekendFacts record={circuit.data?.record} />
    </div>
  );
}

function WeekendBody({ year, race }: { year: number; race: RaceEvent }) {
  const circuit = useRoundCircuit(year, race.round);
  return (
    <div className="space-y-4">
      <div className="grid gap-4 lg:grid-cols-2">
        <WeekendSchedule sessions={race.sessions ?? {}} />
        <Section state={circuit} label="Circuit history" skeletonClassName="h-[300px]" className="h-full">
          <CircuitHistoryPanel record={circuit.data?.record} />
        </Section>
      </div>
      <WeekendStakes year={year} race={race} />
      <WeekendGlance year={year} round={race.round} />
    </div>
  );
}

/**
 * The Weekend tab below the tabs: when each session starts, who won here
 * before and what is at stake. The hero sits above the tabs (`WeekendTop`).
 *
 * Reads the schedule and the circuit, so it renders on a weekend the
 * prediction model has never been run for.
 */
export function WeekendPanel({ year, selectedRace }: { year: number; selectedRace: RaceEvent | null }) {
  if (!selectedRace) {
    return (
      <Panel as="section" className="p-5">
        <p className="text-sm text-rc-ink-2">Pick a race to see its weekend.</p>
      </Panel>
    );
  }
  return <WeekendBody year={year} race={selectedRace} />;
}
