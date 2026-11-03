"use client";

import { Fragment } from "react";

import { LocalTime } from "@/app/components/LocalTime";
import {
  hasDisagreement,
  sourceLine,
  standingsLabel,
  type StandingsFreshness,
  type StandingsSource,
} from "@/app/lib/standingsFreshness";

import { Tooltip } from "./Tooltip";

interface SourceBadgeProps {
  /** A payload's freshness fields (`as_of_round`, `provisional`, `sources`); any may be missing. */
  freshness?: Partial<StandingsFreshness> | null;
  /** When the payload was built (ISO, UTC); shown as "as of …" in the reader's zone. */
  asOf?: string | null;
  className?: string;
}

/** Mono caps at the size of the mockups' notes and eyebrows. */
const BADGE = "font-mono text-[10px] font-medium uppercase leading-none tracking-[0.1em]";
/**
 * Confirmed reads as a quiet caption. Provisional is set apart by shape and
 * brightness (a dashed outline, primary ink), not by a warning colour: it is
 * the normal state for a few hours after every race.
 */
const TONE = {
  confirmed: "text-rc-ink-3",
  provisional: "rounded-sm border border-dashed border-rc-ink-3 px-1.5 py-1 text-rc-ink",
} as const;

type Status = keyof typeof TONE;

/**
 * Where a figure comes from and how settled it is: "after round 19 ·
 * provisional · as of Nov 3, 01:46 UTC".
 *
 * When the payload lists its sources, the badge is a `Tooltip` button whose
 * tooltip names each one (release, rounds, sessions) and how every
 * cross-check came out. A cross-check that disagrees with the served table is also flagged in
 * the badge itself, in red text. Renders nothing when there is neither a round
 * nor a time to show.
 */
export function SourceBadge({ freshness, asOf, className = "" }: SourceBadgeProps) {
  const label = standingsLabel(freshness);
  if (!label && !asOf) return null;

  const status = label ? statusOf(freshness) : undefined;
  const classes = `${BADGE} ${TONE[status ?? "confirmed"]}`;
  const text = <BadgeText label={label} asOf={asOf} disagrees={hasDisagreement(freshness)} />;
  const sources = freshness?.sources ?? [];

  if (sources.length === 0) {
    return (
      <span className={`inline-block ${classes} ${className}`} data-status={status}>
        {text}
      </span>
    );
  }
  return (
    <Tooltip label={text} className={`${classes} ${className}`} data-status={status}>
      <SourceList sources={sources} />
    </Tooltip>
  );
}

function statusOf(freshness: Partial<StandingsFreshness> | null | undefined): Status {
  return freshness?.provisional ? "provisional" : "confirmed";
}

function BadgeText({ label, asOf, disagrees }: { label: string | null; asOf?: string | null; disagrees: boolean }) {
  return (
    <>
      {label}
      {label && asOf ? " · " : null}
      {asOf ? (
        <>
          as of <LocalTime value={asOf} style="stampZone" />
        </>
      ) : null}
      {disagrees ? (
        <>
          {" · "}
          <span className="text-rc-red-text">cross-check differs</span>
        </>
      ) : null}
    </>
  );
}

/** The tooltip's body: one line per source, a disagreeing cross-check in red text. */
function SourceList({ sources }: { sources: StandingsSource[] }) {
  return (
    <>
      {/* The spaces between lines keep them apart in the accessible description, which reads no layout. */}
      <span className={`mb-1 block ${BADGE} text-rc-ink-3`}>Sources</span>
      {sources.map((source, index) => (
        <Fragment key={`${source.role}-${source.source}-${index}`}>
          {" "}
          <span className={`block ${source.status === "disagrees" ? "text-rc-red-text" : ""}`}>
            {sourceLine(source)}
          </span>
        </Fragment>
      ))}
    </>
  );
}
