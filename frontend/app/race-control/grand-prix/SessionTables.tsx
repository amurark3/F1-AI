"use client";

import { getTeamColor } from "@/app/lib/teamColors";

import { shortName } from "./predictionHelpers";

import type { SessionEntry } from "./sessionsModel";

/** Position cell: the number when classified, else f1db's own text (DNF/NC). */
function PositionCell({ entry }: { entry: SessionEntry }) {
  return (
    <td className="px-4 py-2.5 font-mono text-[#8E96A8]">
      {entry.position === null ? (
        <span className="text-[#FF4655]">{entry.position_text}</span>
      ) : (
        `P${entry.position}`
      )}
    </td>
  );
}

function DriverCell({ entry }: { entry: SessionEntry }) {
  return (
    <td className="px-4 py-2.5">
      <span className="flex min-w-0 items-center gap-3">
        <span className="h-4 w-[3px] rounded-full" style={{ background: getTeamColor(entry.team) }} />
        <span className="font-mono text-sm font-black uppercase tracking-[0.06em] text-white">
          {entry.driver_code}
        </span>
        <span className="truncate text-[#AEB5C5]">{shortName(entry.driver_name)}</span>
      </span>
    </td>
  );
}

function Row({ children }: { children: React.ReactNode }) {
  return <tr className="bg-[#0D111B] text-sm text-[#B7BDCA] hover:bg-[#121825]">{children}</tr>;
}

function Head({ labels }: { labels: Array<[string, "left" | "right"]> }) {
  return (
    <thead className="bg-[#0F141E] font-mono text-[10px] uppercase tracking-[0.22em] text-[#6F7789]">
      <tr className="border-b border-[#1E2633]">
        {labels.map(([label, align]) => (
          <th key={label} className={align === "right" ? "px-4 py-3 text-right" : "px-4 py-3 text-left"}>
            {label}
          </th>
        ))}
      </tr>
    </thead>
  );
}

const TABLE_CLASS = "w-full min-w-[620px] border-collapse text-left";

/** Practice: one best lap, the gap to the fastest, and the tour count. */
export function PracticeTable({ entries }: { entries: SessionEntry[] }) {
  return (
    <table className={TABLE_CLASS}>
      <Head
        labels={[
          ["Pos", "left"],
          ["Driver", "left"],
          ["Team", "left"],
          ["Best lap", "right"],
          ["Gap", "right"],
          ["Laps", "right"],
        ]}
      />
      <tbody className="divide-y divide-[#1E2633]">
        {entries.map((entry) => (
          <Row key={entry.driver_code}>
            <PositionCell entry={entry} />
            <DriverCell entry={entry} />
            <td className="px-4 py-2.5 text-[#AEB5C5]">{entry.team || "-"}</td>
            <td className="px-4 py-2.5 text-right font-mono font-bold text-white">{entry.time ?? "-"}</td>
            <td className="px-4 py-2.5 text-right font-mono text-[#8E96A8]">{entry.gap ?? "-"}</td>
            <td className="px-4 py-2.5 text-right font-mono text-[#7F8797]">{entry.laps ?? "-"}</td>
          </Row>
        ))}
      </tbody>
    </table>
  );
}

/** Qualifying: every segment, so an early exit is visible as an empty cell. */
export function QualifyingTable({ entries }: { entries: SessionEntry[] }) {
  return (
    <table className={TABLE_CLASS}>
      <Head
        labels={[
          ["Pos", "left"],
          ["Driver", "left"],
          ["Team", "left"],
          ["Q1", "right"],
          ["Q2", "right"],
          ["Q3", "right"],
          ["Gap", "right"],
        ]}
      />
      <tbody className="divide-y divide-[#1E2633]">
        {entries.map((entry) => (
          <Row key={entry.driver_code}>
            <PositionCell entry={entry} />
            <DriverCell entry={entry} />
            <td className="px-4 py-2.5 text-[#AEB5C5]">{entry.team || "-"}</td>
            {[entry.q1, entry.q2, entry.q3].map((segment, index) => (
              <td
                key={index}
                className={`px-4 py-2.5 text-right font-mono ${segment ? "text-white" : "text-[#3F4756]"}`}
              >
                {segment ?? "-"}
              </td>
            ))}
            <td className="px-4 py-2.5 text-right font-mono text-[#8E96A8]">{entry.gap ?? "-"}</td>
          </Row>
        ))}
      </tbody>
    </table>
  );
}

/** Sprint race: the result, with what it paid and where it started from. */
export function RaceTable({ entries }: { entries: SessionEntry[] }) {
  return (
    <table className={TABLE_CLASS}>
      <Head
        labels={[
          ["Pos", "left"],
          ["Driver", "left"],
          ["Team", "left"],
          ["Grid", "right"],
          ["Time / gap", "right"],
          ["Laps", "right"],
          ["Pts", "right"],
        ]}
      />
      <tbody className="divide-y divide-[#1E2633]">
        {entries.map((entry) => (
          <Row key={entry.driver_code}>
            <PositionCell entry={entry} />
            <DriverCell entry={entry} />
            <td className="px-4 py-2.5 text-[#AEB5C5]">{entry.team || "-"}</td>
            <td className="px-4 py-2.5 text-right font-mono text-[#8E96A8]">
              {entry.grid === null ? "-" : `P${entry.grid}`}
            </td>
            <td className="px-4 py-2.5 text-right font-mono text-white">
              {entry.retired ? (
                <span className="text-[#FF4655]">{entry.retired}</span>
              ) : (
                (entry.gap ?? entry.time ?? "-")
              )}
            </td>
            <td className="px-4 py-2.5 text-right font-mono text-[#7F8797]">{entry.laps ?? "-"}</td>
            {/* Nullish, not falsy: a driver who scored 0 finished the sprint,
                which is a different fact from having no points recorded. */}
            <td className="px-4 py-2.5 text-right font-mono font-bold text-white">{entry.points ?? "-"}</td>
          </Row>
        ))}
      </tbody>
    </table>
  );
}
