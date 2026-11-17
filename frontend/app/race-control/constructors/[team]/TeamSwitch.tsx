"use client";

import Link from "next/link";

import { API_BASE } from "@/app/constants/api";
import { teamHref } from "@/app/lib/entityLinks";
import { TeamName } from "@/app/ui/names/TeamName";
import { Section } from "@/app/ui/section/Section";
import { useSection } from "@/app/ui/section/useSection";

import { profilesUrl, type SeasonDirectory } from "../../profiles/profilesModel";

const REFRESH = { revalidateOnFocus: false, dedupingInterval: 180_000 };

const LINK =
  "inline-flex items-center gap-[7px] rounded border border-transparent px-2.5 py-[7px] font-mono text-[11px] font-medium uppercase leading-none tracking-[0.08em]";

interface TeamSwitchProps {
  year: number;
  /** The team the page is about. */
  teamId: string;
  /** The server render's directory; null renders the skeleton and fetches in the browser. */
  seed: SeasonDirectory | null;
}

/** Every team of the season, one click apart, in table order. */
export function TeamSwitch({ year, teamId, seed }: TeamSwitchProps) {
  const state = useSection<SeasonDirectory>(profilesUrl(API_BASE, year, "directory"), { seed, config: REFRESH });
  return (
    <Section state={state} label="Teams" skeletonClassName="h-9">
      <nav aria-label="Teams" className="flex flex-wrap gap-1.5">
        {state.data?.teams.map((team) => {
          const current = team.id === teamId;
          return (
            <Link
              key={team.id}
              href={teamHref(team.id)}
              aria-current={current ? "page" : undefined}
              className={`${LINK} ${current ? "border-rc-line bg-rc-raised text-rc-ink" : "text-rc-ink-3 hover:text-rc-ink"}`}
            >
              <i aria-hidden="true" className="size-2 rounded-[2px]" style={{ backgroundColor: team.color }} />
              <TeamName name={team.name} fullName={team.full_name} id={team.id} year={year} />
            </Link>
          );
        })}
      </nav>
    </Section>
  );
}
