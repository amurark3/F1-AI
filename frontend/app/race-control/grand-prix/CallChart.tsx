"use client";

import { getTeamColor } from "@/app/lib/teamColors";
import { Legend } from "@/app/ui/Legend";
import { DriverName } from "@/app/ui/names/DriverName";
import { PanelHeading } from "@/app/ui/PanelHeading";
import { rc } from "@/app/ui/tokens";

import { Panel } from "../components/RaceControlPrimitives";
import { DriverLink } from "../profiles/EntityLinks";

import {
  chartTitle,
  DNF_FLAG_PCT,
  trackPercent,
  trackSize,
  type OutRow,
  type PlacedRow,
  type ReviewRow,
} from "./reviewModel";

export interface DriverIdentity {
  name: string;
  team: string;
}

export type IdentityLookup = Record<string, DriverIdentity>;

const ROW =
  "grid min-h-[30px] grid-cols-[30px_44px_1fr_36px] items-center gap-x-2 border-b border-rc-line-soft sm:grid-cols-[40px_150px_1fr_44px] sm:gap-x-3";
const VALUE = "text-right font-mono text-xs font-semibold";
const LEGEND = [
  { label: "The call", color: rc.ink3, mark: "outline" },
  { label: "The classified result, in the team's colour", color: rc.ink2 },
  { label: "A retirement scores no places" },
] as const;

/** `+2` finished ahead of the call, `−2` behind it, `0` exactly where called. */
export function deltaText(delta: number): string {
  if (delta === 0) return "0";
  return delta > 0 ? `+${delta}` : `−${Math.abs(delta)}`;
}

function Who({ code, identity }: { code: string; identity: DriverIdentity }) {
  return (
    <span className="inline-flex min-w-0 items-center gap-2 text-[13px] font-semibold text-rc-ink">
      <span
        className="h-3.5 w-[3px] shrink-0 rounded-full max-sm:hidden"
        style={{ background: getTeamColor(identity.team) }}
      />
      <DriverLink code={code} name={identity.name}>
        <DriverName
          variant="codeLast"
          code={code}
          name={identity.name}
          className="max-sm:[&>span:first-child]:hidden"
        />
      </DriverLink>
    </span>
  );
}

function Track({ children }: { children: React.ReactNode }) {
  return (
    <span className="relative block h-3" aria-hidden="true">
      <span className="absolute inset-x-0 top-1/2 border-t border-rc-line-soft" />
      {children}
    </span>
  );
}

const MARK = "absolute top-1/2 -translate-x-1/2 -translate-y-1/2 rounded-full";

function Ring({ at }: { at: number }) {
  return <i className={`${MARK} size-[11px] border-2 border-rc-ink-3 bg-(--surface)`} style={{ left: `${at}%` }} />;
}

function PlacedLine({ row, size, identity }: { row: PlacedRow; size: number; identity: DriverIdentity }) {
  const call = trackPercent(row.called, size);
  const result = trackPercent(row.finished, size);
  return (
    <>
      <Track>
        <b
          className="absolute top-[5px] h-0.5 origin-left rounded-[1px] bg-rc-ink-3 motion-safe:animate-fill-x"
          style={{ left: `${Math.min(call, result)}%`, width: `${Math.abs(result - call)}%` }}
        />
        <Ring at={call} />
        <i className={`${MARK} size-[7px]`} style={{ left: `${result}%`, background: getTeamColor(identity.team) }} />
      </Track>
      <span className={`${VALUE} text-rc-ink-2`} title={`Called P${row.called}, finished P${row.finished}`}>
        {deltaText(row.delta)}
        <span className="sr-only">
          {" "}
          (called P{row.called}, finished P{row.finished})
        </span>
      </span>
    </>
  );
}

function riskNote(row: OutRow): string {
  if (row.risk === null) return "no risk figure stored";
  return row.flagged ? `risk ${row.risk}%, flagged` : `risk ${row.risk}%, under the ${DNF_FLAG_PCT}% flag`;
}

function OutLine({ row, size }: { row: OutRow; size: number }) {
  return (
    <>
      <Track>
        <Ring at={trackPercent(row.called, size)} />
      </Track>
      <span className={`${VALUE} text-rc-red-text`}>{row.status}</span>
    </>
  );
}

function ChartRow({ row, size, identity }: { row: ReviewRow; size: number; identity: DriverIdentity }) {
  return (
    <li className={ROW}>
      <span className="font-mono text-xs font-semibold text-rc-ink-3">P{row.called}</span>
      <Who code={row.code} identity={identity} />
      {row.kind === "placed" ? (
        <PlacedLine row={row} size={size} identity={identity} />
      ) : (
        <OutLine row={row} size={size} />
      )}
      {row.kind === "out" && (
        <p className="col-span-2 col-start-3 pb-1.5 text-[11px] text-rc-ink-3">
          {row.detail} · {riskNote(row)} · no place delta
        </p>
      )}
    </li>
  );
}

/**
 * One row per called car, in called order: a ring at the call, a dot at the
 * classified result and the gap between. A retirement has the ring and `DNF`,
 * never a dot or a number.
 */
export function CallChart({
  rows,
  identities,
  surnameOf,
}: {
  rows: ReviewRow[];
  identities: IdentityLookup;
  surnameOf: (code: string) => string;
}) {
  const size = trackSize(rows);
  return (
    <Panel as="section" className="p-5">
      <PanelHeading
        eyebrow="Call against result"
        title={chartTitle(rows, surnameOf)}
        sub="Rows in called order · + finished ahead of the call, − behind it · the classified result, never a retirement's listed place"
      />
      <ul>
        {rows.map((row) => (
          <ChartRow
            key={row.code}
            row={row}
            size={size}
            identity={identities[row.code] ?? { name: row.code, team: "" }}
          />
        ))}
      </ul>
      <Legend items={LEGEND} label="Call against result key" className="mt-3.5" />
    </Panel>
  );
}
