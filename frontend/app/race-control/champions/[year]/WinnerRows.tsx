"use client";

import { use } from "react";

import type { SeasonDetail } from "@/app/lib/server/champions";
import { getTeamColor } from "@/app/lib/teamColors";
import { StateTag } from "@/app/race-control/grand-prix/StateTag";
import { DriverLink, TeamLink } from "@/app/race-control/profiles/EntityLinks";
import { DriverName } from "@/app/ui/names/DriverName";
import { TeamName } from "@/app/ui/names/TeamName";
import { Section } from "@/app/ui/section/Section";
import { EYEBROW } from "@/app/ui/typography";

import { useSeasonDetail } from "../useChampionsSections";

import { roundsAside, seasonSource, toRunRow, winnerRows, type WinnerRow } from "./seasonDetailModel";

const NOTE = "font-mono text-[10px] font-medium uppercase leading-[1.6] tracking-[0.1em] text-rc-ink-3";

function Winners({ row, season, linkable }: { row: WinnerRow; season: number; linkable: boolean }) {
  return (
    <p className="truncate text-sm font-semibold text-rc-ink">
      {row.winners.map((w, i) => {
        const name = <DriverName name={w.winner} id={w.driver_id} year={season} />;
        return (
          <span key={w.winner}>
            {i > 0 && " / "}
            {linkable ? (
              <DriverLink id={w.driver_id} name={w.winner}>
                {name}
              </DriverLink>
            ) : (
              name
            )}
          </span>
        );
      })}
    </p>
  );
}

function Row({ row, season, linkable }: { row: WinnerRow; season: number; linkable: boolean }) {
  const team = row.team ? <TeamName name={row.team} id={row.teamId} year={season} /> : null;
  return (
    <li className="grid min-h-[58px] break-inside-avoid grid-cols-[30px_3px_minmax(0,1fr)_40px] items-center gap-2.5 border-b border-rc-line-soft py-2 sm:grid-cols-[36px_3px_minmax(0,1fr)_auto_44px] sm:gap-3">
      <span className={`font-mono text-xs font-semibold ${row.decider ? "text-rc-gold" : "text-rc-ink-3"}`}>
        R{row.round}
      </span>
      <i
        aria-hidden="true"
        className="h-5 w-[3px] rounded-[1px]"
        style={{ backgroundColor: getTeamColor(row.team ?? "") }}
      />
      <div className="min-w-0">
        <Winners row={row} season={season} linkable={linkable} />
        <p className="mt-[3px] truncate text-xs text-rc-ink-3">
          {row.decider && <StateTag tone="gold">Title decided</StateTag>}
          {row.decider && " "}
          {row.shared && <StateTag>Shared drive</StateTag>}
          {row.shared && " "}
          {team && <span className="sm:hidden">{team} · </span>}
          {row.raceName}
        </p>
      </div>
      <span className="hidden whitespace-nowrap text-xs text-rc-ink-2 sm:block">
        {team &&
          (linkable ? (
            <TeamLink id={row.teamId} name={row.team}>
              {team}
            </TeamLink>
          ) : (
            team
          ))}
      </span>
      <span className="whitespace-nowrap text-right font-mono text-[11px] font-medium text-rc-ink-3">{row.date}</span>
    </li>
  );
}

function ToRun({ span, text }: { span: string; text: string }) {
  return (
    <li className="flex min-h-12 break-inside-avoid items-center gap-2.5 border-b border-rc-line-soft py-2 sm:gap-3">
      <span className="min-w-[30px] font-mono text-xs font-semibold text-rc-ink-3 sm:min-w-9">{span}</span>
      <i aria-hidden="true" className="h-5 w-[3px] rounded-[1px] bg-rc-dim" />
      <p className="font-mono text-[11px] font-medium uppercase tracking-[0.08em] text-rc-ink-3">{text}</p>
    </li>
  );
}

/** The head's caption: how many rounds are in. Paints nothing until the season's data is. */
export function RoundsAside({ year, seed }: { year: number; seed: Promise<SeasonDetail | null> }) {
  const d = useSeasonDetail(year, use(seed)).data;
  return d ? <p className={EYEBROW}>{roundsAside(d)}</p> : null;
}

/** Every race's winner in round order, shared drives folded, then the rounds still to run. */
export function WinnerRows({
  year,
  seed,
  linkable,
}: {
  year: number;
  seed: Promise<SeasonDetail | null>;
  linkable: boolean;
}) {
  const state = useSeasonDetail(year, use(seed));
  const d = state.data;
  const rows = d ? winnerRows(d) : [];
  const toRun = d ? toRunRow(d) : null;
  return (
    <Section state={state} label={`${year} season`} skeletonClassName="h-[560px]" className="mt-6">
      {d && (
        <>
          {rows.length === 0 && <p className="text-sm text-rc-ink-3">No race has a result yet.</p>}
          {(rows.length > 0 || toRun) && (
            <ol
              aria-label={`${d.season} race winners`}
              className="border-t border-rc-line min-[1100px]:columns-2 min-[1100px]:gap-x-12"
            >
              {rows.map((row) => (
                <Row key={row.round} row={row} season={d.season} linkable={linkable} />
              ))}
              {toRun && <ToRun {...toRun} />}
            </ol>
          )}
          <p className={`mt-3.5 ${NOTE}`}>{seasonSource(d)}</p>
        </>
      )}
    </Section>
  );
}
