import { getTeamColor } from "@/app/lib/teamColors";
import { DriverName } from "@/app/ui/names/DriverName";
import { TeamName } from "@/app/ui/names/TeamName";

import { DriverLink, TeamLink } from "../profiles/EntityLinks";

import {
  penaltyLabel,
  positionLabel,
  stoppedLabel,
  timeLabel,
  type ResultRow,
  type SessionResult,
} from "./resultsModel";

const HEAD = "pr-2.5 pb-2.5 font-mono text-[10px] font-semibold uppercase leading-none tracking-[0.16em] text-rc-ink-3";
const CELL = "border-b border-rc-line-soft py-2.5 pr-2.5 align-middle";
const COLUMNS = 5;

/** The winner's numeral is gold; a non-finisher's word is red text, never a place. */
function positionTone(row: ResultRow): string {
  if (row.position === null) return "text-rc-red-text";
  return row.position === 1 ? "text-rc-gold" : "text-rc-ink-2";
}

function PositionCell({ row }: { row: ResultRow }) {
  const tone = positionTone(row);
  return <td className={`${CELL} w-10 font-mono text-[13px] font-semibold sm:w-12 ${tone}`}>{positionLabel(row)}</td>;
}

function DriverCell({ row, year }: { row: ResultRow; year: number }) {
  return (
    <td className={CELL}>
      <span className="inline-flex items-center gap-2.5 font-semibold text-rc-ink">
        <span className="h-4 w-[3px] shrink-0 rounded-full" style={{ background: getTeamColor(row.team) }} />
        <DriverLink code={row.driver_code} name={row.driver_name}>
          <DriverName variant="codeLast" code={row.driver_code} name={row.driver_name} year={year} />
        </DriverLink>
      </span>
      {row.fastest_lap && (
        <span className="ml-1.5 inline-block rounded-sm bg-(--f1-sector-best)/15 px-1.5 py-1 align-middle font-mono text-[10px] font-medium uppercase leading-none tracking-[0.1em] text-(--f1-sector-best)">
          Fastest lap
        </span>
      )}
    </td>
  );
}

function TimeCell({ row }: { row: ResultRow }) {
  if (row.position === null) {
    return <td className={`${CELL} text-right font-mono text-[13px] text-rc-red-text`}>{stoppedLabel(row)}</td>;
  }
  const penalty = penaltyLabel(row);
  return (
    <td className={`${CELL} text-right font-mono text-[13px] text-rc-ink`}>
      {timeLabel(row)}
      {penalty && <span className="block text-[11px] text-rc-ink-3">{penalty}</span>}
    </td>
  );
}

function ResultLine({ row, year }: { row: ResultRow; year: number }) {
  return (
    <tr>
      <PositionCell row={row} />
      <DriverCell row={row} year={year} />
      <td className={`${CELL} whitespace-nowrap text-[13px] text-rc-ink-3 max-sm:hidden`}>
        <TeamLink name={row.team}>
          <TeamName name={row.team} />
        </TeamLink>
      </td>
      <TimeCell row={row} />
      <td className={`${CELL} pr-0 text-right font-mono text-[13px] ${row.points ? "text-rc-ink" : "text-rc-ink-3"}`}>
        {row.points ?? "—"}
      </td>
    </tr>
  );
}

/** Classified cars first, then a labelled cut and everyone who is not a finisher. */
export function ResultsTable({ result, year }: { result: SessionResult; year: number }) {
  const rows = result.classification;
  const firstOut = rows.findIndex((row) => row.position === null);

  return (
    <table className="w-full border-collapse text-left text-sm">
      <thead>
        <tr className="border-b border-rc-line">
          <th className={HEAD}>Pos</th>
          <th className={HEAD}>Driver</th>
          <th className={`${HEAD} max-sm:hidden`}>Team</th>
          <th className={`${HEAD} text-right`}>Time / gap</th>
          <th className={`${HEAD} pr-0 text-right`}>Pts</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((row, index) => (
          <FragmentRow key={row.driver_code} row={row} year={year} cut={index === firstOut} />
        ))}
      </tbody>
    </table>
  );
}

function FragmentRow({ row, year, cut }: { row: ResultRow; year: number; cut: boolean }) {
  return (
    <>
      {cut && (
        <tr>
          <td
            colSpan={COLUMNS}
            className="border-b border-dashed border-rc-line pt-4 pb-2 font-mono text-[10px] font-semibold uppercase leading-none tracking-[0.16em] text-rc-red-text"
          >
            Did not finish
          </td>
        </tr>
      )}
      <ResultLine row={row} year={year} />
    </>
  );
}
