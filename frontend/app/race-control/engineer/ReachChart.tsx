"use client";

import { getTeamColor, NEUTRAL_TEAM_COLOR } from "@/app/lib/teamColors";
import { DriverName } from "@/app/ui/names/DriverName";
import { TeamName } from "@/app/ui/names/TeamName";
import { RankBars, type RankBarItem } from "@/app/ui/RankBars";
import { EYEBROW } from "@/app/ui/typography";

import type { ReachChartData, ReachRow } from "./engineerModel";

const NUMBER = new Intl.NumberFormat("en");

function item(row: ReachRow, chart: ReachChartData): RankBarItem {
  return {
    id: row.key,
    label:
      chart.championship === "drivers" ? (
        <DriverName variant="last" name={row.name} code={row.key} year={chart.year} />
      ) : (
        <TeamName name={row.key} year={chart.year} />
      ),
    value: row.points,
    reach: row.max,
    valueText: `${NUMBER.format(row.points)} → ${NUMBER.format(row.max)}`,
    // An empty team would match the first livery in the table, so it gets the neutral colour.
    color: row.team ? getTeamColor(row.team) : NEUTRAL_TEAM_COLOR,
  };
}

/**
 * Points today against the most each row can still reach, from a standings
 * tool's own numbers: the title is computed there too, never written here.
 */
export function ReachChart({ chart }: { chart: ReachChartData }) {
  return (
    <figure className="my-2 rounded-md border border-rc-line bg-(--surface) px-[18px] py-4">
      <figcaption className={`${EYEBROW} leading-snug`}>{chart.title}</figcaption>
      <RankBars
        className="mt-3"
        label={chart.title}
        max={Math.max(...chart.rows.map((row) => row.max))}
        items={chart.rows.map((row) => item(row, chart))}
      />
    </figure>
  );
}
