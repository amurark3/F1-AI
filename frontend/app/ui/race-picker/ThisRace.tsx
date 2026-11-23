"use client";

import { Lock } from "lucide-react";
import Link from "next/link";

import { API_BASE } from "@/app/constants/api";
import type { RaceEvent } from "@/app/race-control/grand-prix/predictionModel";
import type { RaceResultsResponse } from "@/app/race-control/grand-prix/resultsModel";

import { useSection } from "../section/useSection";
import { RACES, RACE_VIEWS, type RaceView } from "../shell/navConfig";
import { EYEBROW } from "../typography";

import { raceQuery } from "./raceUrl";

const RESULT_CONFIG = { revalidateOnFocus: false, dedupingInterval: 120_000 };
const ITEM = "relative py-2 font-display text-[15px] font-bold uppercase tracking-wide sm:py-3";

/** The four views of the selected race, using a published race classification to unlock the post-race views. */
export function ThisRace({ year, race, view }: { year: number; race: RaceEvent; view: RaceView }) {
  const { round } = race;
  const results = useSection<RaceResultsResponse>(
    race.status === "upcoming" ? null : `${API_BASE}/api/race-control/results/${year}/${round}`,
    { config: RESULT_CONFIG },
  );
  const classified = Boolean(results.data?.race?.classification.length);
  const query = raceQuery(round, year);

  return (
    <nav
      aria-label="This race"
      className="grid grid-cols-4 items-baseline justify-items-start border-b border-rc-line sm:flex sm:flex-wrap sm:gap-x-7"
    >
      <span className={`${EYEBROW} hidden sm:inline`}>This race · R{round}</span>
      {RACES.links.map((link) => {
        const here = RACE_VIEWS[view].href === link.href ? "page" : undefined;
        const label = "switcherLabel" in link ? link.switcherLabel : link.label;
        return "afterRace" in link && !classified ? (
          <button
            key={link.href}
            type="button"
            disabled
            aria-current={here}
            className={`${ITEM} inline-flex items-center gap-1.5 text-rc-ink-3 disabled:cursor-not-allowed`}
          >
            {label}
            <Lock aria-hidden="true" className="size-3 shrink-0" />
          </button>
        ) : (
          <Link
            key={link.href}
            href={`${link.href}?${query}`}
            aria-current={here}
            prefetch={false}
            className={`${ITEM} text-rc-ink-3 hover:text-rc-ink aria-[current=page]:text-rc-ink aria-[current=page]:after:absolute aria-[current=page]:after:inset-x-0 aria-[current=page]:after:-bottom-px aria-[current=page]:after:h-0.5 aria-[current=page]:after:bg-f1-red`}
          >
            {label}
          </Link>
        );
      })}
    </nav>
  );
}
