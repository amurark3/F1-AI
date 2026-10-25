"use client";

import { ArrowDown } from "lucide-react";
import { useState } from "react";

import { ConsoleHeader, ConsolePanel } from "../../grand-prix/predictionConsole";
import {
  OVER_COLOR,
  PENDING_COLOR,
  outcomeLabel,
  partShortWhere,
  partWhere,
  type CarEvent,
  type ElementInfo,
  type ElementUsage,
  type Part,
  type PowerUnitCar,
  type RoundInfo,
} from "../powerUnitsModel";

interface PartKey {
  code: string;
  number: number;
}

const ORDINALS = ["", "1st", "2nd", "3rd"];
const ordinal = (n: number): string => ORDINALS[n] ?? `${n}th`;

function tileStyle(part: Part, teamColor: string): React.CSSProperties {
  if (part.not_counted_from !== null) {
    return { borderColor: "#3A4354", background: "transparent", opacity: 0.6 };
  }
  if (part.beyond_allowance) {
    return { borderColor: OVER_COLOR, background: `${OVER_COLOR}2E` };
  }
  return { borderColor: `${teamColor}80`, background: `${teamColor}1F` };
}

function UnitTile({
  part,
  teamColor,
  rounds,
  active,
  onActivate,
}: {
  part: Part;
  teamColor: string;
  rounds: Map<number, RoundInfo>;
  active: boolean;
  onActivate: (key: PartKey) => void;
}) {
  const where = partShortWhere(part, rounds);
  const activate = () => onActivate({ code: part.code, number: part.number });
  return (
    <button
      type="button"
      onMouseEnter={activate}
      onFocus={activate}
      onClick={activate}
      aria-pressed={active}
      aria-label={`${part.code} unit ${part.number}: ${partWhere(part, rounds)}`}
      className={`relative flex h-12 w-14 flex-col items-center justify-center rounded border font-mono transition-transform hover:-translate-y-0.5 focus-visible:outline-none ${
        part.round === null ? "border-dashed" : ""
      } ${active ? "ring-2 ring-white/70" : ""}`}
      style={tileStyle(part, teamColor)}
    >
      <span
        className={`text-[13px] font-black leading-none text-white ${part.not_counted_from !== null ? "line-through" : ""}`}
      >
        #{part.number}
      </span>
      <span className="mt-1 text-[9px] font-bold uppercase tracking-[0.08em] text-[#B7BDCA]">{where}</span>
      {part.beyond_allowance && part.not_counted_from === null && (
        <span
          className="absolute -right-1 -top-1 h-2.5 w-2.5 rounded-full border-2 border-[#0D111B]"
          style={{ background: OVER_COLOR }}
        />
      )}
    </button>
  );
}

function ElementRow({
  usage,
  info,
  teamColor,
  rounds,
  active,
  onActivate,
}: {
  usage: ElementUsage;
  info: ElementInfo | undefined;
  teamColor: string;
  rounds: Map<number, RoundInfo>;
  active: PartKey | null;
  onActivate: (key: PartKey) => void;
}) {
  const allowance = usage.allowance ?? usage.used;
  const counted = usage.parts.filter((part) => part.not_counted_from === null);
  const uncounted = usage.parts.filter((part) => part.not_counted_from !== null);
  const within = counted.filter((part) => part.number <= allowance);
  const beyond = counted.filter((part) => part.number > allowance);
  const tile = (part: Part) => (
    <UnitTile
      key={part.number}
      part={part}
      teamColor={teamColor}
      rounds={rounds}
      active={active?.code === part.code && active.number === part.number}
      onActivate={onActivate}
    />
  );
  return (
    <div className="flex flex-col gap-3 px-4 py-4 md:flex-row md:items-center">
      <div className="w-full shrink-0 md:w-44">
        <p className="font-mono text-sm font-black tracking-[0.08em] text-white">{usage.code}</p>
        <p className="text-[11px] text-[#6F7789]">{info?.name}</p>
        <p className="mt-1 font-mono text-xs tabular-nums text-[#B7BDCA]">
          {usage.used} used / {usage.allowance ?? "?"} allowed
          {usage.over_by > 0 && (
            <span
              className="ml-2 rounded px-1.5 py-0.5 text-[10px] font-black text-white"
              style={{ background: OVER_COLOR }}
            >
              +{usage.over_by}
            </span>
          )}
        </p>
      </div>
      <div className="flex min-w-0 flex-wrap items-center gap-2">
        {within.map(tile)}
        {Array.from({ length: Math.max(0, allowance - within.length) }, (_, index) => (
          <span
            key={`free-${index}`}
            className="flex h-12 w-14 items-center justify-center rounded border border-dashed border-[#2C3646] font-mono text-[9px] uppercase tracking-[0.12em] text-[#4A5263]"
          >
            spare
          </span>
        ))}
        {beyond.length > 0 && (
          <span className="flex h-12 flex-col items-center justify-center px-1" aria-hidden="true">
            <span className="h-8 border-l-2 border-dashed" style={{ borderColor: OVER_COLOR }} />
            <span
              className="mt-0.5 font-mono text-[8px] font-black uppercase tracking-[0.14em]"
              style={{ color: OVER_COLOR }}
            >
              limit
            </span>
          </span>
        )}
        {beyond.map(tile)}
        {uncounted.length > 0 && (
          <span className="ml-1 font-mono text-[9px] uppercase tracking-[0.14em] text-[#5A6273]">not counted</span>
        )}
        {uncounted.map(tile)}
      </div>
    </div>
  );
}

function rulingFor(part: Part, events: CarEvent[]): string {
  if (part.not_counted_from !== null) {
    return `The FIA's usage reports stopped counting this unit from round ${part.not_counted_from}, so it is not in the total.`;
  }
  const event = events.find((item) => item.round === part.round);
  const decision = event?.decisions.find((item) =>
    item.elements.some((element) => element.code === part.code && element.number === part.number),
  );
  if (decision) {
    const session = decision.session ? `, first used in ${decision.session}` : "";
    return `Stewards: ${outcomeLabel(decision)}${session}.`;
  }
  if (!part.beyond_allowance) {
    return "No penalty — within the season's allowance.";
  }
  if (event?.penalty_status === "pending") {
    return "The stewards' decision for this weekend has not been published yet.";
  }
  return "No stewards' decision naming this unit was found in the collected documents.";
}

function Inspector({
  part,
  usage,
  events,
  rounds,
}: {
  part: Part;
  usage: ElementUsage;
  events: CarEvent[];
  rounds: Map<number, RoundInfo>;
}) {
  const allowance = usage.allowance;
  const extra = allowance === null ? 0 : part.number - allowance;
  const tone = part.beyond_allowance ? OVER_COLOR : "#00FF78";
  return (
    <div className="border-t border-[#1E2633] bg-[#0A0E16] px-4 py-3" aria-live="polite">
      <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
        <div className="min-w-0">
          <p className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]" style={{ color: tone }}>
            {part.code} #{part.number} ·{" "}
            {extra > 0 ? `${ordinal(extra)} beyond the ${allowance} allowed` : `within the ${allowance ?? "?"} allowed`}
          </p>
          <p className="mt-1 text-sm text-white">{partWhere(part, rounds)}.</p>
          <p className="mt-0.5 text-sm" style={{ color: part.beyond_allowance ? "#FFB4B1" : "#8E96A8" }}>
            {rulingFor(part, events)}
          </p>
        </div>
        {part.round !== null && (
          <a
            href={`#round-${part.round}`}
            className="inline-flex shrink-0 items-center gap-1.5 font-mono text-[10px] font-bold uppercase tracking-[0.16em] text-[#9EC5FF] hover:text-white"
          >
            That weekend <ArrowDown className="h-3 w-3" aria-hidden="true" />
          </a>
        )}
      </div>
    </div>
  );
}

function defaultPart(car: PowerUnitCar): PartKey | null {
  const parts = car.elements.flatMap((item) => item.parts);
  const latest = [...parts].sort(
    (a, b) => (b.round ?? 0) - (a.round ?? 0) || Number(b.beyond_allowance) - Number(a.beyond_allowance),
  )[0];
  return latest ? { code: latest.code, number: latest.number } : null;
}

export function ElementLedger({
  car,
  elements,
  rounds,
  teamColor,
}: {
  car: PowerUnitCar;
  elements: ElementInfo[];
  rounds: Map<number, RoundInfo>;
  teamColor: string;
}) {
  const [active, setActive] = useState<PartKey | null>(() => defaultPart(car));
  const info = new Map(elements.map((item) => [item.code, item]));
  const activeUsage = car.elements.find((item) => item.code === active?.code);
  const activePart = activeUsage?.parts.find((part) => part.number === active?.number);

  return (
    <ConsolePanel>
      <ConsoleHeader
        label="Element ledger"
        right={
          <span className="hidden items-center gap-3 font-mono text-[10px] uppercase tracking-[0.14em] text-[#7F8797] sm:inline-flex">
            <span className="inline-flex items-center gap-1.5">
              <span className="h-2.5 w-2.5 rounded-sm" style={{ background: teamColor }} /> within
            </span>
            <span className="inline-flex items-center gap-1.5">
              <span className="h-2.5 w-2.5 rounded-sm" style={{ background: OVER_COLOR }} /> beyond
            </span>
            <span className="inline-flex items-center gap-1.5">
              <span className="h-2.5 w-2.5 rounded-sm border border-dashed" style={{ borderColor: PENDING_COLOR }} />{" "}
              round not named
            </span>
          </span>
        }
      />
      <div className="divide-y divide-[#1E2633]">
        {car.elements.map((usage) => (
          <ElementRow
            key={usage.code}
            usage={usage}
            info={info.get(usage.code)}
            teamColor={teamColor}
            rounds={rounds}
            active={active}
            onActivate={setActive}
          />
        ))}
      </div>
      {activePart && activeUsage && (
        <Inspector part={activePart} usage={activeUsage} events={car.events} rounds={rounds} />
      )}
    </ConsolePanel>
  );
}
