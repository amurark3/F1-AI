"use client";

import { use } from "react";

import type { DriverChampion, SeasonDetail } from "@/app/lib/server/champions";
import { getTeamColor } from "@/app/lib/teamColors";
import { Legend } from "@/app/ui/Legend";
import { PanelHeading } from "@/app/ui/PanelHeading";
import { Section } from "@/app/ui/section/Section";

import { useSeasonDetail } from "../useChampionsSections";

import { ribbonLegend, ribbonTitle, roundTicks, type RoundTick } from "./seasonDetailModel";

const FLAG =
  "absolute -top-9 whitespace-nowrap font-mono text-[10px] font-semibold uppercase leading-none tracking-[0.12em] text-rc-gold";

function Tick({ tick }: { tick: RoundTick }) {
  return (
    <li title={tick.tip} className="relative grid grid-rows-[12px_28px_auto] items-end">
      <span className="sr-only">{tick.tip}</span>
      {tick.decider && <i aria-hidden="true" className="absolute -top-6 left-1/2 -ml-px h-9 w-0.5 bg-rc-gold" />}
      {tick.flag && (
        <span className={`${FLAG} ${tick.flag.side === "end" ? "right-1/2 -mr-px" : "left-1/2 -ml-px"}`}>
          {tick.flag.text}
        </span>
      )}
      <i
        aria-hidden="true"
        className={`size-[5px] self-center justify-self-center rounded-full ${tick.championWon ? "relative z-[1] bg-rc-ink" : ""}`}
      />
      {tick.run ? (
        <b
          aria-hidden="true"
          className="block h-7 rounded-[2px] opacity-90"
          style={{ backgroundColor: getTeamColor(tick.team ?? "") }}
        />
      ) : (
        <b aria-hidden="true" className="block h-2.5 rounded-[2px] bg-rc-dim" />
      )}
      <span
        aria-hidden="true"
        className={`mt-2 block text-center font-mono text-[10px] leading-none ${
          tick.decider ? "font-semibold text-rc-gold" : "font-medium text-rc-ink-3"
        } ${tick.keep ? "" : "max-sm:invisible"}`}
      >
        {tick.round}
      </span>
    </li>
  );
}

function Ribbon({ d, driver }: { d: SeasonDetail; driver: DriverChampion }) {
  const title = ribbonTitle(d, driver);
  return (
    <figure className="rounded-md border border-rc-line bg-(--surface) p-[18px] sm:p-6">
      <PanelHeading eyebrow="Round by round" title={title} />
      <ol
        aria-label={`${d.season}, round by round: ${title}`}
        className="mt-[18px] grid gap-0.5 pt-9 sm:gap-1"
        style={{ gridTemplateColumns: `repeat(${d.round_count}, minmax(0, 1fr))` }}
      >
        {roundTicks(d).map((tick) => (
          <Tick key={tick.round} tick={tick} />
        ))}
      </ol>
      <Legend className="mt-4" items={ribbonLegend(d, driver)} />
    </figure>
  );
}

/** One tick per round: the winning car's team, the champion's wins, and the round that decided the title. */
export function RoundByRound({ year, seed }: { year: number; seed: Promise<SeasonDetail | null> }) {
  const state = useSeasonDetail(year, use(seed));
  const d = state.data;
  return (
    <Section state={state} label={`${year} season`} skeletonClassName="h-[220px]">
      {d?.driver_champion && <Ribbon d={d} driver={d.driver_champion} />}
    </Section>
  );
}
