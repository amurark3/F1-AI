import { Legend } from "@/app/ui/Legend";
import { DriverName } from "@/app/ui/names/DriverName";
import { teamLabel } from "@/app/ui/names/names";
import { barStaggerMs } from "@/app/ui/rankBarScale";
import { rc } from "@/app/ui/tokens";

import { finishSentence, statusCode } from "../../profiles/finishes";

import { heatCell, type HeatKind } from "./teamModel";

import type { TeamDriver, TeamProfile, TeamRound } from "../../profiles/profilesModel";

const CELL =
  "grid h-10 min-w-6 place-items-center rounded-[3px] font-mono text-[13px] font-semibold motion-safe:animate-fade-up";

const LOOK: Record<HeatKind, string> = {
  future: "border border-dashed border-rc-line",
  absent: "text-rc-ink-3",
  out: "border border-rc-red-text/60 text-[10px] text-rc-red-text",
  p1: "bg-rc-gold text-background",
  p2: "bg-rc-silver text-background",
  p3: "bg-rc-bronze text-background",
  points: "text-rc-ink",
  plain: "bg-rc-ink/3 text-rc-ink-2",
};

/** The team's colour at the strength of a points finish. */
function tint(color: string): string {
  return `color-mix(in srgb, ${color} 16%, transparent)`;
}

interface CellProps {
  round: TeamRound;
  driver: TeamDriver;
  profile: TeamProfile;
}

function Cell({ round, driver, profile }: CellProps) {
  const result = round.results.find((item) => item.driver_id === driver.id);
  const { kind, finish } = heatCell(round, result);
  const label = `R${round.round} ${round.short_name}`;
  const name = teamLabel({ id: profile.team.id, name: profile.team.name, year: profile.year }, "name");
  let sentence = `${label}: still to run`;
  let text = "";
  if (kind === "absent") {
    sentence = `${label}: did not race for ${name}`;
    text = "—";
  } else if (finish) {
    sentence = finishSentence(label, finish);
    text = kind === "out" ? statusCode(finish) : String(finish.position);
  }
  return (
    <td className="p-0">
      <span
        title={sentence}
        className={`${CELL} ${LOOK[kind]}`}
        style={{
          animationDelay: `${barStaggerMs(round.round - 1)}ms`,
          backgroundColor: kind === "points" ? tint(profile.team.color) : undefined,
        }}
      >
        {text}
        <span className="sr-only">{sentence}</span>
      </span>
    </td>
  );
}

function Header({ rounds }: { rounds: TeamRound[] }) {
  const last = rounds.filter((round) => round.status === "complete").at(-1)?.round;
  return (
    <thead>
      <tr>
        <th scope="col" className="sticky left-0 bg-(--background)">
          <span className="sr-only">Driver</span>
        </th>
        {rounds.map((round) => (
          <th
            key={round.round}
            scope="col"
            className={`pb-1 text-center font-mono text-[10px] font-medium ${round.round === last ? "text-rc-ink" : "text-rc-ink-3"}`}
          >
            R{round.round}
          </th>
        ))}
      </tr>
    </thead>
  );
}

function DriverCell({ driver, year }: { driver: TeamDriver; year: number }) {
  const identity = { name: driver.name, lastName: driver.last_name, code: driver.code, id: driver.id, year };
  return (
    <th
      scope="row"
      className="sticky left-0 z-10 bg-(--background) pr-3 text-left text-[13px] font-semibold whitespace-nowrap text-rc-ink"
    >
      <DriverName {...identity} variant="code" className="sm:hidden" />
      <DriverName {...identity} variant="codeLast" className="max-sm:hidden" />
    </th>
  );
}

/** Every finish of every driver who raced for the team, one cell per round of the season. */
export function TeamHeatGrid({ profile }: { profile: TeamProfile }) {
  const { team, rounds, drivers, year } = profile;
  const caption = `${teamLabel({ id: team.id, name: team.name, year }, "name")} race results by round`;
  return (
    <div>
      <div className="overflow-x-auto">
        <table
          className="w-full border-separate border-spacing-1"
          style={{ minWidth: `${rounds.length * 28 + 120}px` }}
        >
          <caption className="sr-only">{caption}</caption>
          <Header rounds={rounds} />
          <tbody>
            {drivers.map((driver) => (
              <tr key={driver.id}>
                <DriverCell driver={driver} year={year} />
                {rounds.map((round) => (
                  <Cell key={round.round} round={round} driver={driver} profile={profile} />
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <Legend
        label="Heat grid key"
        className="mt-4"
        items={[
          { label: "Win", color: rc.gold },
          { label: "P2", color: rc.silver },
          { label: "P3", color: rc.bronze },
          { label: "Points", color: tint(team.color) },
          { label: "Did not finish or start", color: rc.redText, mark: "outline" },
          { label: "Still to run", color: rc.line, mark: "outline" },
        ]}
      />
    </div>
  );
}
