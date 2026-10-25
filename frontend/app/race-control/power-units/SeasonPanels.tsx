/**
 * The season overview's supporting panels: every stewards' decision of the
 * season, and where every number on the screen came from.
 *
 * Server-safe: no state, no effects.
 */
import { ExternalLink, FileWarning, FileX2, Gavel } from "lucide-react";
import Link from "next/link";

import { getTeamColor } from "@/app/lib/teamColors";

import { InlineNotice } from "../components/RaceControlPrimitives";
import { ConsoleHeader, ConsolePanel } from "../grand-prix/predictionConsole";

import {
  OVER_COLOR,
  carHref,
  outcomeLabel,
  penaltyLog,
  shortDay,
  type ElementInfo,
  type PowerUnitCar,
  type PowerUnitsResponse,
  type RoundInfo,
  type WithdrawnDocument,
} from "./powerUnitsModel";

export function FiaLink({ href, label }: { href: string; label: string }) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="inline-flex items-center gap-1 font-mono text-[10px] uppercase tracking-[0.14em] text-[#9EC5FF] hover:text-white"
    >
      {label}
      <ExternalLink className="h-3 w-3" aria-hidden="true" />
      <span className="sr-only">(opens the FIA document)</span>
    </a>
  );
}

export function PenaltyLog({ cars, rounds }: { cars: PowerUnitCar[]; rounds: Map<number, RoundInfo> }) {
  const entries = penaltyLog(cars);
  return (
    <ConsolePanel>
      <ConsoleHeader
        label="Stewards' decisions"
        right={
          <span className="inline-flex items-center gap-2 font-mono text-[10px] uppercase tracking-[0.18em] text-[#7F8797]">
            <Gavel className="h-3.5 w-3.5 text-[#F5C542]" />
            {entries.length} this season
          </span>
        }
      />
      {entries.length === 0 ? (
        <p className="p-4 text-sm text-[#8E96A8]">No power-unit decision has been published this season.</p>
      ) : (
        <ol className="max-h-[560px] divide-y divide-[#1E2633] overflow-y-auto">
          {entries.map(({ car, event, decision }) => {
            const color = getTeamColor(car.team);
            const driver = event.driver ?? car.driver;
            return (
              <li key={`${decision.url}-${car.seat_id}`} className="flex items-start gap-3 px-4 py-3">
                <span className="w-10 shrink-0 font-mono text-[11px] font-bold text-[#7F8797]">
                  {rounds.get(event.round)?.code ?? `R${event.round}`}
                </span>
                <span className="mt-1 h-4 w-[3px] shrink-0 rounded-full" style={{ background: color }} />
                <div className="min-w-0 flex-1">
                  <Link href={carHref(car)} className="text-sm font-bold text-white hover:underline">
                    #{driver.car_number} {driver.name}
                  </Link>
                  <p className="mt-0.5 truncate font-mono text-[10px] uppercase tracking-[0.12em] text-[#6F7789]">
                    {decision.elements.map((item) => `${item.code} #${item.number}`).join(" · ")}
                  </p>
                </div>
                <div className="flex shrink-0 flex-col items-end gap-1">
                  <span className="font-mono text-xs font-black" style={{ color: OVER_COLOR }}>
                    {outcomeLabel(decision)}
                  </span>
                  <FiaLink href={decision.url} label={decision.number ? `Doc ${decision.number}` : "FIA doc"} />
                </div>
              </li>
            );
          })}
        </ol>
      )}
    </ConsolePanel>
  );
}

export function AllowanceLegend({ elements }: { elements: ElementInfo[] }) {
  return (
    <ConsolePanel>
      <ConsoleHeader label="2026 allowance per car" />
      <dl className="grid grid-cols-2 gap-px bg-[#1E2633] sm:grid-cols-4">
        {elements.map((item) => (
          <div key={item.code} className="bg-[#0D111B] px-3 py-3">
            <dt className="font-mono text-[10px] uppercase tracking-[0.16em] text-[#7F8797]">{item.code}</dt>
            <dd className="mt-1 font-mono text-2xl font-black text-white">{item.allowance ?? "?"}</dd>
            <dd className="mt-1 text-[11px] leading-snug text-[#6F7789]">{item.name}</dd>
            <dd className="mt-2">
              <AllowanceOrigin item={item} />
            </dd>
          </div>
        ))}
        <div className="bg-[#0D111B] px-3 py-3">
          <dt className="font-mono text-[10px] uppercase tracking-[0.16em] text-[#7F8797]">Source</dt>
          <dd className="mt-1 text-[11px] leading-snug text-[#6F7789]">
            Each link opens the FIA report that last stated the figure, dated by its Grand Prix.
          </dd>
        </div>
      </dl>
      <p className="border-t border-[#1E2633] px-4 py-3 text-xs leading-relaxed text-[#8E96A8]">
        Each figure is the latest one the FIA&apos;s own reports state, collected with the rest of the documents — so a
        change to the regulations shows up here without a release. The first unit beyond an allowance costs ten grid
        places, every later one of the same element five, and a weekend&apos;s penalties add up (Article B8.2.8).
      </p>
    </ConsolePanel>
  );
}

function AllowanceOrigin({ item }: { item: ElementInfo }) {
  const origin = item.allowance_source;
  if (!origin) {
    return <span className="font-mono text-[9px] uppercase tracking-[0.12em] text-[#F5C542]">not stated yet</span>;
  }
  if (origin.kind === "manual") {
    return (
      <span
        className="font-mono text-[9px] uppercase tracking-[0.12em] text-[#F5C542]"
        title={origin.note ?? undefined}
      >
        pinned by hand
      </span>
    );
  }
  return origin.url ? <FiaLink href={origin.url} label={`FIA · ${shortDay(origin.stated_on) || "report"}`} /> : null;
}

function WithdrawnList({ items }: { items: WithdrawnDocument[] }) {
  return (
    <InlineNotice title={`${items.length} FIA document(s) withdrawn or replaced — not counted`} tone="info">
      <ul className="mt-1 space-y-1">
        {items.map((item) => (
          <li key={`${item.url}-${item.reason}`} className="flex flex-wrap items-center gap-2">
            <FileX2 className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
            <span className="line-through decoration-[#5A6273]">{item.title}</span>
            <span className="text-[#8E96A8]">— {item.reason}</span>
            <FiaLink href={item.url} label="Open" />
          </li>
        ))}
      </ul>
    </InlineNotice>
  );
}

/** Where every number came from, and what the collection could not read. */
export function Provenance({ data }: { data: PowerUnitsResponse }) {
  return (
    <div className="flex flex-col gap-3">
      {data.unread.length > 0 && (
        <InlineNotice title={`${data.unread.length} FIA document(s) could not be read`} tone="warning">
          <ul className="mt-1 space-y-1">
            {data.unread.map((item) => (
              <li key={item.url} className="flex flex-wrap items-center gap-2">
                <FileWarning className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
                <span>
                  {item.event}: {item.title} — {item.reason}
                </span>
                <FiaLink href={item.url} label="Open" />
              </li>
            ))}
          </ul>
          <p className="mt-2 text-xs">Counts that depend on these documents may be incomplete until they are read.</p>
        </InlineNotice>
      )}
      {(data.withdrawn ?? []).length > 0 && <WithdrawnList items={data.withdrawn ?? []} />}
      {data.warnings.length > 0 && (
        <InlineNotice title="Checks that did not add up" tone="warning">
          <ul className="list-disc space-y-1 pl-4">
            {data.warnings.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </InlineNotice>
      )}
      <InlineNotice title="Where these numbers come from">
        <ul className="list-disc space-y-1 pl-4">
          {(data.notes ?? []).map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      </InlineNotice>
    </div>
  );
}
