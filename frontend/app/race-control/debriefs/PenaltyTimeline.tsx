import { DriverName } from "@/app/ui/names/DriverName";
import { PanelHeading } from "@/app/ui/PanelHeading";

import { StateTag } from "../grand-prix/StateTag";

import { penaltySub, penaltyTitle } from "./lapsModel";

import type { DebriefPenalties, InRacePenalty, PostRacePenalty } from "./debriefTypes";

const CARD = "rounded-md border border-rc-line bg-(--surface) p-5 sm:p-6";

function Row({
  lap,
  code,
  name,
  tag,
  detail,
}: {
  lap: string;
  code: string;
  name: string;
  tag: string;
  detail: string;
}) {
  return (
    <li className="grid grid-cols-[76px_1fr] gap-3 border-b border-rc-line-soft py-[11px]">
      <span className="font-mono text-[11px] font-semibold leading-relaxed text-rc-ink-3">{lap}</span>
      <div className="min-w-0">
        <p className="flex flex-wrap items-center gap-2">
          <DriverName name={name} code={code} className="font-semibold" />
          <StateTag tone="red">{tag}</StateTag>
        </p>
        {detail && <p className="mt-0.5 text-xs text-rc-ink-3">{detail}</p>}
      </div>
    </li>
  );
}

const tagOf = (seconds: number | null, text: string) => (seconds === null ? text : `${seconds} s`);

function inRaceDetail(row: InRacePenalty): string {
  return [row.offence, row.served ? "served" : null].filter(Boolean).join(" · ");
}

function postRaceDetail(row: PostRacePenalty): string {
  const moved = row.road_position !== null && row.position !== null ? `P${row.road_position} → P${row.position}` : null;
  return [row.reason, row.document === null ? null : `FIA doc ${row.document}`, moved].filter(Boolean).join(" · ");
}

/** Penalties as the stewards gave them: in-race from race control, then post-race from the FIA. */
export function PenaltyTimeline({ penalties }: { penalties: DebriefPenalties }) {
  const empty = penalties.in_race.length + penalties.post_race.length === 0;
  return (
    <div className={CARD}>
      <PanelHeading
        eyebrow="Penalties"
        title={penalties.available ? penaltyTitle(penalties) : undefined}
        sub={penalties.available ? penaltySub(penalties) : undefined}
      />
      {!penalties.available && (
        <p className="text-sm text-rc-ink-3">OpenF1 has no race control record for this race.</p>
      )}
      {!empty && (
        <ol aria-label="Penalties">
          {penalties.in_race.map((row) => (
            <Row
              key={`in-${row.car}-${row.lap}-${row.penalty}`}
              lap={row.lap === null ? "In race" : `L${row.lap}`}
              code={row.driver_code}
              name={row.driver_name}
              tag={tagOf(row.seconds, row.penalty)}
              detail={inRaceDetail(row)}
            />
          ))}
          {penalties.post_race.map((row) => (
            <Row
              key={`post-${row.driver_code}-${row.document}-${row.ruling}`}
              lap="Post-race"
              code={row.driver_code}
              name={row.driver_name}
              tag={tagOf(row.seconds, row.ruling)}
              detail={postRaceDetail(row)}
            />
          ))}
        </ol>
      )}
    </div>
  );
}
