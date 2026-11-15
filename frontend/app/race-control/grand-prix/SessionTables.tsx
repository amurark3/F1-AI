"use client";

import { getTeamColor } from "@/app/lib/teamColors";
import { DriverName } from "@/app/ui/names/DriverName";

import { DriverLink } from "../profiles/EntityLinks";

import {
  fastestByPart,
  gapFraction,
  isDsq,
  lastTime,
  PARTS,
  qualifyingGroups,
  timeMs,
  type QualifyingGroup,
} from "./qualifyingModel";
import { StateTag } from "./StateTag";

import type { PracticeEntry, QualifyingEntry, QualifyingPart, SessionEntry } from "./sessionsModel";

const HEAD = "pr-2.5 pb-2.5 font-mono text-[10px] font-semibold uppercase leading-none tracking-[0.16em] text-rc-ink-3";
const CELL = "border-b border-rc-line-soft py-2.5 pr-2.5 align-middle";
const NUM = "text-right font-mono text-[13px]";
const PURPLE = "font-semibold text-(--f1-sector-best)";

function positionTone(position: number | null): string {
  if (position === null) return "text-rc-red-text";
  return position === 1 ? "text-rc-gold" : "text-rc-ink-2";
}

/** The number when classified, else the word f1db prints (DSQ, DNF, NC) in red text. */
function PositionCell({ entry }: { entry: SessionEntry }) {
  const tone = positionTone(entry.position);
  return (
    <td className={`${CELL} w-10 font-mono text-[13px] font-semibold sm:w-12 ${tone}`}>
      {entry.position ?? entry.position_text}
    </td>
  );
}

function Who({ entry }: { entry: SessionEntry }) {
  return (
    <span className="inline-flex items-center gap-2.5 font-semibold text-rc-ink">
      <span className="h-4 w-[3px] shrink-0 rounded-full" style={{ background: getTeamColor(entry.team) }} />
      <DriverLink code={entry.driver_code} name={entry.driver_name}>
        <DriverName variant="codeLast" code={entry.driver_code} name={entry.driver_name} />
      </DriverLink>
    </span>
  );
}

function DriverCell({ entry, children }: { entry: SessionEntry; children?: React.ReactNode }) {
  return (
    <td className={CELL}>
      <Who entry={entry} />
      {children && (
        <span className="ml-2 inline-block align-middle max-sm:mt-1 max-sm:ml-0 max-sm:block">{children}</span>
      )}
    </td>
  );
}

/** Practice: one best lap, the gap to the fastest, and the laps run. A stand-in names whose car it drove. */
export function PracticeTable({ entries, label = "Practice" }: { entries: PracticeEntry[]; label?: string }) {
  return (
    <table className="w-full border-collapse text-left text-sm">
      <thead>
        <tr className="border-b border-rc-line">
          <th className={HEAD}>Pos</th>
          <th className={HEAD}>Driver</th>
          <th className={`${HEAD} text-right`}>Best lap</th>
          <th className={`${HEAD} text-right`}>Gap</th>
          <th className={`${HEAD} pr-0 text-right`}>Laps</th>
        </tr>
      </thead>
      <tbody>
        {entries.map((entry) => (
          <tr key={entry.driver_code}>
            <PositionCell entry={entry} />
            <DriverCell entry={entry}>
              {entry.stand_in_for && (
                <StateTag>
                  {label} run ·{" "}
                  <DriverName
                    variant="last"
                    code={entry.stand_in_for.driver_code}
                    name={entry.stand_in_for.driver_name}
                  />
                  &rsquo;s car
                </StateTag>
              )}
            </DriverCell>
            <td className={`${CELL} ${NUM} ${entry.position === 1 ? PURPLE : "text-rc-ink"}`}>{entry.time ?? "—"}</td>
            <td className={`${CELL} ${NUM} text-rc-ink-2`}>{entry.gap ?? "—"}</td>
            <td className={`${CELL} ${NUM} pr-0 text-rc-ink-3`}>{entry.laps ?? "—"}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

const COLUMNS = 8;

function PartTime({
  entry,
  part,
  best,
}: {
  entry: QualifyingEntry;
  part: QualifyingPart;
  best: Partial<Record<QualifyingPart, number>>;
}) {
  const time = entry[part];
  const fastest = time !== null && !isDsq(entry) && timeMs(time) === best[part];
  const tone = fastest ? PURPLE : "text-rc-ink";
  return <td className={`${CELL} ${NUM} max-sm:hidden ${time ? tone : "text-rc-ink-3"}`}>{time ?? "—"}</td>;
}

function PromotedTag({ entry }: { entry: QualifyingEntry }) {
  if (entry.promoted_by.length === 0) return null;
  return (
    <StateTag>
      Up {entry.promoted_by.length} · {entry.promoted_by.join(", ")} DSQ
    </StateTag>
  );
}

function GapCell({ entry }: { entry: QualifyingEntry }) {
  if (entry.part_gap === null) {
    return <td className={`${CELL} ${NUM} pr-0 text-rc-ink-3`}>{entry.position === 1 ? "POLE" : "—"}</td>;
  }
  return <td className={`${CELL} ${NUM} pr-0 text-rc-ink`}>{entry.part_gap}</td>;
}

function GapBar({ entry, entries }: { entry: QualifyingEntry; entries: QualifyingEntry[] }) {
  return (
    <td className={`${CELL} w-[26%] max-sm:hidden`}>
      <span className="block h-2 rounded bg-rc-line-soft">
        <span
          className="block h-2 origin-left rounded motion-safe:animate-fill-x"
          style={{ width: `${gapFraction(entry, entries) * 100}%`, background: getTeamColor(entry.team) }}
        />
      </span>
    </td>
  );
}

function QualifyingLine({
  entry,
  entries,
  best,
}: {
  entry: QualifyingEntry;
  entries: QualifyingEntry[];
  best: Partial<Record<QualifyingPart, number>>;
}) {
  const last = lastTime(entry);
  return (
    <tr>
      <PositionCell entry={entry} />
      <DriverCell entry={entry}>
        <PromotedTag entry={entry} />
      </DriverCell>
      {PARTS.map((part) => (
        <PartTime key={part} entry={entry} part={part} best={best} />
      ))}
      <td className={`${CELL} ${NUM} text-rc-ink sm:hidden`}>
        {last ? (
          <>
            <span className="mr-1 text-rc-ink-3">{last.part}</span>
            {last.time}
          </>
        ) : (
          "—"
        )}
      </td>
      <GapBar entry={entry} entries={entries} />
      <GapCell entry={entry} />
    </tr>
  );
}

function Group({
  group,
  entries,
  best,
}: {
  group: QualifyingGroup;
  entries: QualifyingEntry[];
  best: Partial<Record<QualifyingPart, number>>;
}) {
  return (
    <>
      {group.cut && (
        <tr>
          <td
            colSpan={COLUMNS}
            className={`border-b border-dashed border-rc-line pt-4 pb-2 font-mono text-[10px] font-semibold uppercase leading-none tracking-[0.16em] ${group.disqualified ? "text-rc-red-text" : "text-rc-ink-3"}`}
          >
            {group.cut}
          </td>
        </tr>
      )}
      {group.rows.map((entry) => (
        <QualifyingLine key={entry.driver_code} entry={entry} entries={entries} best={best} />
      ))}
    </>
  );
}

/**
 * Qualifying: every part, grouped by the part each car ran in, with the gap inside that part
 * (the official figure). Purple is the fastest lap of a part.
 */
export function QualifyingTable({ entries }: { entries: QualifyingEntry[] }) {
  const best = fastestByPart(entries);
  return (
    <table className="w-full border-collapse text-left text-sm">
      <thead>
        <tr className="border-b border-rc-line">
          <th className={HEAD}>Pos</th>
          <th className={HEAD}>Driver</th>
          {PARTS.map((part) => (
            <th key={part} className={`${HEAD} text-right max-sm:hidden`}>
              {part.toUpperCase()}
            </th>
          ))}
          <th className={`${HEAD} text-right sm:hidden`}>Time</th>
          <th className={`${HEAD} max-sm:hidden`}>Gap in their part</th>
          <th className={`${HEAD} pr-0 text-right`}>Gap</th>
        </tr>
      </thead>
      <tbody>
        {qualifyingGroups(entries).map((group) => (
          <Group key={group.key} group={group} entries={entries} best={best} />
        ))}
      </tbody>
    </table>
  );
}
