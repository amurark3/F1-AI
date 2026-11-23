import { LocalTime } from "@/app/components/LocalTime";
import { DriverName } from "@/app/ui/names/DriverName";
import { TeamName } from "@/app/ui/names/TeamName";

import { FinalTag, StateTag } from "../grand-prix/StateTag";

import {
  carCounts,
  changesResult,
  docLabel,
  isCorrected,
  outcomesText,
  printedSubject,
  REASON_LABEL,
  type DeletedLaps,
  type FeedEvent,
  type StartingGrid,
  type StewardsDecision,
} from "./fiaFeedModel";

const DOC_LINK =
  "inline-block whitespace-nowrap font-mono text-[11px] font-medium leading-normal text-rc-ink-2 underline decoration-rc-line underline-offset-[3px] hover:text-rc-ink hover:decoration-rc-ink-3";

const LINE_ONE = "flex flex-wrap items-baseline gap-x-2.5 gap-y-1 text-sm leading-snug";
const LINE_TWO = "mt-1 text-xs leading-normal text-rc-ink-3";

function plural(count: number, noun: string): string {
  return `${count} ${noun}${count === 1 ? "" : "s"}`;
}

function kindLabel(event: FeedEvent): string {
  if (event.unread !== null) return "Document";
  if (event.kind === "penalty") return event.data?.status === "summoned" ? "Summons" : "Decision";
  return event.kind === "grid" ? "Grid" : "Deleted laps";
}

function DecisionLine({
  data,
  year,
  withdrawn,
  result,
}: {
  data: StewardsDecision;
  year: number;
  withdrawn: boolean;
  result: boolean;
}) {
  const summoned = data.status === "summoned";
  const outcome = summoned ? "Summoned" : outcomesText(data);
  const quiet = data.outcomes.length > 0 && data.outcomes.every((item) => item.kind === "no_further_action");
  let outcomeTone = "text-rc-ink-2";
  if (!withdrawn && result) outcomeTone = "font-semibold text-rc-ink";
  else if (withdrawn || quiet) outcomeTone = "text-rc-ink-3";
  const nameTone = withdrawn ? "text-rc-ink-3 line-through decoration-rc-ink-3" : "text-rc-ink";
  const identity = { year };
  let name = <span>Car {data.car}</span>;
  if (data.driver) name = <DriverName name={data.driver} {...identity} />;
  else if (data.competitor) name = <TeamName name={data.competitor} {...identity} />;
  const detail = summoned
    ? [data.offence, data.hearing ? `hearing ${data.hearing} circuit time` : null]
    : [data.session, data.offence, ...data.articles];
  return (
    <>
      <p className={LINE_ONE}>
        <span className={`font-semibold ${nameTone}`}>{name}</span>
        <span className="-ml-1 font-mono text-[11px] text-rc-ink-3">#{data.car}</span>
        <span className={outcomeTone}>
          <span className="text-rc-ink-3">— </span>
          {outcome}
        </span>
      </p>
      <p className={LINE_TWO}>{detail.filter((part) => part).join(" · ")}</p>
    </>
  );
}

function DeletedLapsLine({ data, withdrawn }: { data: DeletedLaps; withdrawn: boolean }) {
  const counts = carCounts(data.laps);
  return (
    <>
      <p className={LINE_ONE}>
        <span className={`font-semibold ${withdrawn ? "text-rc-ink-3" : "text-rc-ink"}`}>
          {plural(data.laps.length, "lap time")} deleted
        </span>
        <span className={withdrawn ? "text-rc-ink-3" : "text-rc-ink-2"}>— {data.session}</span>
      </p>
      <p className={LINE_TWO}>
        {REASON_LABEL[data.reason]} · {plural(counts.length, "car")}
      </p>
      <p className="mt-2 flex flex-wrap gap-1.5">
        {counts.map(({ car, count, entrant }) => (
          <span
            key={car}
            title={entrant}
            className="rounded-sm bg-white/[0.06] px-1.5 py-1 font-mono text-[11px] leading-none text-rc-ink-2"
          >
            #{car}
            <span className="ml-[3px] text-rc-ink-3">×{count}</span>
          </span>
        ))}
      </p>
    </>
  );
}

function GridLine({ data }: { data: StartingGrid }) {
  return (
    <>
      <p className={LINE_ONE}>
        <span className="font-semibold text-rc-ink">{data.final ? "Final" : "Provisional"} starting grid</span>
        <FinalTag final={data.final} />
      </p>
      <ul className="mt-1.5 grid gap-1">
        {data.penalties.map((note) => (
          <li key={`${note.car}-${note.ruling}`} className="text-[13px] text-rc-ink-2">
            <span className="mr-2 font-mono text-[11px] text-rc-ink-3">#{note.car}</span>
            {note.ruling}
            {note.reason && <span className="ml-2 text-xs text-rc-ink-3">{note.reason}</span>}
          </li>
        ))}
        {data.penalties.length === 0 && <li className="text-[13px] text-rc-ink-3">No grid penalties</li>}
      </ul>
    </>
  );
}

function EventBody({ event, year }: { event: FeedEvent; year: number }) {
  const withdrawn = event.withdrawn !== null;
  if (event.unread !== null || event.data === null) {
    return (
      <>
        <p className={LINE_ONE}>
          <span className="font-semibold text-rc-ink">{printedSubject(event.title)}</span>
        </p>
        <p className={LINE_TWO}>Couldn&rsquo;t read this PDF yet; open it for the decision.</p>
      </>
    );
  }
  if (event.kind === "penalty") {
    return <DecisionLine data={event.data} year={year} withdrawn={withdrawn} result={changesResult(event)} />;
  }
  if (event.kind === "deleted_laps") return <DeletedLapsLine data={event.data} withdrawn={withdrawn} />;
  return <GridLine data={event.data as StartingGrid} />;
}

/** One FIA document in the feed: when, what kind, what it says, and a link to the PDF. */
export function FiaFeedRow({ event, year }: { event: FeedEvent; year: number }) {
  const rule = changesResult(event) ? "border-l-f1-red" : "border-l-transparent";
  const colStart = "col-start-2 md:col-start-auto";
  return (
    <li
      className={`grid grid-cols-[56px_minmax(0,1fr)] gap-x-3 gap-y-1.5 border-b border-l-2 border-b-rc-line-soft py-3 pl-2.5 md:grid-cols-[72px_92px_minmax(0,1fr)_auto] md:items-start md:gap-x-4 md:pl-3 ${rule}`}
    >
      <p className="row-span-3 flex flex-col gap-1 md:row-span-1">
        <span className="font-mono text-[13px] font-semibold leading-none text-rc-ink">
          <LocalTime value={event.published_at} style="clock" />
        </span>
        <span className="whitespace-nowrap font-mono text-[10px] leading-none text-rc-ink-3">
          <LocalTime value={event.published_at} style="weekday" />
        </span>
      </p>
      <p
        className={`${colStart} font-mono text-[9px] font-semibold uppercase leading-[13px] tracking-[0.16em] text-rc-ink-3`}
      >
        {kindLabel(event)}
      </p>
      <div className={`min-w-0 ${colStart}`}>
        <EventBody event={event} year={year} />
        {(isCorrected(event.title) || event.withdrawn !== null) && (
          <p className="mt-1.5 flex gap-1.5">
            {isCorrected(event.title) && <StateTag>Corrected</StateTag>}
            {event.withdrawn !== null && <StateTag>Withdrawn</StateTag>}
          </p>
        )}
        {event.withdrawn !== null && <p className="mt-1 text-xs text-rc-ink-3">Withdrawn: {event.withdrawn}</p>}
      </div>
      <a
        href={event.url}
        target="_blank"
        rel="noopener noreferrer"
        className={`${DOC_LINK} ${colStart} justify-self-start md:justify-self-auto`}
      >
        {docLabel(event)} ↗<span className="sr-only">(opens the FIA document)</span>
      </a>
    </li>
  );
}
