"use client";

import { useState } from "react";

import { PanelHeading } from "@/app/ui/PanelHeading";
import { Section } from "@/app/ui/section/Section";
import { SectionHead } from "@/app/ui/SectionHead";

import { StateTag } from "../../grand-prix/StateTag";
import {
  partShortWhere,
  partWhere,
  roundsByNumber,
  type ElementInfo,
  type Part,
  type PowerUnitCar,
  type RoundInfo,
} from "../powerUnitsModel";

import {
  defaultPart,
  inspectorHead,
  ledgerRows,
  ledgerTitle,
  rulingFor,
  tileLabel,
  type LedgerRow,
  type PartKey,
} from "./carModel";
import { useCar, type CarSectionProps } from "./useCar";

const SUB =
  "Units in the order fitted, each with the Grand Prix it arrived at. Right of the red line is beyond the allocation. Select a unit for its ruling.";

const BOX = "flex h-[46px] w-[50px] flex-none items-center justify-center rounded-[3px] sm:w-14";

interface TileProps {
  part: Part;
  rounds: Map<number, RoundInfo>;
  pressed: boolean;
  onSelect: (key: PartKey) => void;
}

function Tile({ part, rounds, pressed, onSelect }: TileProps) {
  const counted = part.not_counted_from === null;
  let look = "border border-rc-line bg-rc-raised";
  if (!counted) look = "border border-dotted border-rc-line bg-transparent";
  else if (part.beyond_allowance) look = "border border-f1-red bg-f1-red/16";
  return (
    <button
      type="button"
      aria-pressed={pressed}
      aria-label={tileLabel(part, rounds)}
      onClick={() => onSelect({ code: part.code, number: part.number })}
      className={`${BOX} flex-col font-mono hover:border-rc-ink-3 ${look} ${part.round === null ? "border-dashed" : ""} ${
        pressed ? "ring-1 ring-rc-ink ring-offset-2 ring-offset-background" : ""
      }`}
    >
      <b className={`text-[13px] font-semibold leading-none ${counted ? "text-rc-ink" : "text-rc-ink-3 line-through"}`}>
        #{part.number}
      </b>
      <span
        className={`mt-[5px] text-[9px] font-medium leading-none tracking-[0.1em] ${counted && part.beyond_allowance ? "text-rc-ink-2" : "text-rc-ink-3"}`}
      >
        {partShortWhere(part, rounds)}
      </span>
    </button>
  );
}

function Row({
  row,
  rounds,
  selected,
  onSelect,
}: {
  row: LedgerRow;
  rounds: Map<number, RoundInfo>;
  selected: PartKey | null;
  onSelect: (key: PartKey) => void;
}) {
  const { usage } = row;
  const tile = (part: Part) => (
    <Tile
      key={part.number}
      part={part}
      rounds={rounds}
      pressed={selected?.code === part.code && selected.number === part.number}
      onSelect={onSelect}
    />
  );
  return (
    <div className="grid gap-3 border-t border-rc-line-soft py-4 md:grid-cols-[210px_minmax(0,1fr)] md:gap-6">
      <div>
        <b className="font-mono text-sm font-semibold leading-none tracking-[0.06em] text-rc-ink">{usage.code}</b>
        <small className="mt-[5px] block text-xs text-rc-ink-3">{row.name}</small>
        <p className="mt-2 flex items-center gap-2 font-mono text-xs font-medium leading-none text-rc-ink-2">
          {usage.used} used / {usage.allowance ?? "?"} allowed
          {usage.over_by > 0 && <StateTag tone="red">+{usage.over_by}</StateTag>}
        </p>
      </div>
      <div className="flex flex-wrap items-center gap-1.5">
        {row.within.map(tile)}
        {Array.from({ length: row.spares }, (_, index) => (
          <span
            key={`spare-${index}`}
            className={`${BOX} border border-dashed border-rc-line font-mono text-[9px] font-medium uppercase leading-none tracking-[0.12em] text-rc-ink-3`}
          >
            spare
          </span>
        ))}
        {row.beyond.length > 0 && (
          <span aria-hidden="true" className="mx-0.5 grid w-3.5 place-items-center">
            <i className="h-[46px] w-0.5 bg-f1-red" />
          </span>
        )}
        {row.beyond.map(tile)}
        {row.notCounted.length > 0 && (
          <span className="ml-2 font-mono text-[9px] font-medium uppercase leading-none tracking-[0.14em] text-rc-ink-3">
            Not counted
          </span>
        )}
        {row.notCounted.map(tile)}
      </div>
    </div>
  );
}

function Swatch({ className }: { className: string }) {
  return <i aria-hidden="true" className={`inline-block h-3 w-3.5 rounded-[2px] border ${className}`} />;
}

function LedgerLegend() {
  return (
    <ul
      aria-label="Legend"
      className="flex flex-wrap gap-x-[18px] gap-y-2 border-t border-rc-line-soft pt-4 font-mono text-[11px] font-medium leading-none text-rc-ink-3"
    >
      <li className="inline-flex items-center gap-[7px]">
        <Swatch className="border-rc-line bg-rc-raised" />
        Within the allocation
      </li>
      <li className="inline-flex items-center gap-[7px]">
        <Swatch className="border-f1-red bg-f1-red/16" />
        Beyond the allocation
      </li>
      <li className="inline-flex items-center gap-[7px]">
        <Swatch className="border-dashed border-rc-line" />
        Spare: still available
      </li>
      <li className="inline-flex items-center gap-[7px]">
        <Swatch className="border-dashed border-rc-line bg-rc-raised" />
        Round not pinned down
      </li>
      <li className="inline-flex items-center gap-[7px]">
        <s className="font-semibold">#4</s>
        No longer counted by the FIA
      </li>
    </ul>
  );
}

function Inspector({
  car,
  selected,
  rounds,
}: {
  car: PowerUnitCar;
  selected: PartKey | null;
  rounds: Map<number, RoundInfo>;
}) {
  const usage = car.elements.find((item) => item.code === selected?.code);
  const part = usage?.parts.find((item) => item.number === selected?.number);
  return (
    <div
      aria-live="polite"
      className="-mx-[18px] -mb-[18px] mt-5 flex flex-col items-start justify-between gap-x-6 gap-y-3 rounded-b-md border-t border-rc-line bg-rc-raised px-[18px] py-4 sm:-mx-6 sm:-mb-6 sm:flex-row sm:items-center sm:px-6"
    >
      {usage && part && (
        <>
          <div>
            <p
              className={`font-mono text-[11px] font-semibold uppercase leading-none tracking-[0.22em] ${part.beyond_allowance ? "text-rc-red-text" : "text-rc-ink-3"}`}
            >
              {inspectorHead(part, usage)}
            </p>
            <p className="mt-2 text-rc-ink">{partWhere(part, rounds)}.</p>
            <p className="mt-0.5 text-rc-ink-2">{rulingFor(part, car.events)}</p>
          </div>
          {part.round !== null && car.events.some((event) => event.round === part.round) && (
            <a
              href={`#round-${part.round}`}
              className="flex-none font-mono text-[11px] font-medium uppercase leading-none tracking-[0.12em] text-rc-ink-2 hover:text-rc-ink"
            >
              That weekend ↓
            </a>
          )}
        </>
      )}
    </div>
  );
}

function Ledger({
  car,
  elements,
  rounds,
}: {
  car: PowerUnitCar;
  elements: ElementInfo[];
  rounds: Map<number, RoundInfo>;
}) {
  const [selected, setSelected] = useState<PartKey | null>(() => defaultPart(car));
  return (
    <figure className="rounded-md border border-rc-line bg-(--surface) p-[18px] sm:p-6">
      <PanelHeading eyebrow="Element ledger" title={ledgerTitle(car)} sub={SUB} />
      {ledgerRows(car, elements).map((row) => (
        <Row key={row.usage.code} row={row} rounds={rounds} selected={selected} onSelect={setSelected} />
      ))}
      <LedgerLegend />
      <Inspector car={car} selected={selected} rounds={rounds} />
    </figure>
  );
}

/** 01: one tile per unit fitted, and the ruling for the one selected. */
export function ElementLedger(props: CarSectionProps) {
  const { state, data, car, absent } = useCar(props);
  if (absent) return null;
  return (
    <section aria-labelledby="pu-car-elements">
      <SectionHead index={1} id="pu-car-elements" title="Elements" aside="One tile per unit fitted" />
      <Section state={state} label="Element ledger" skeletonClassName="h-[720px]">
        {car && data && (
          <Ledger key={car.seat_id} car={car} elements={data.elements ?? []} rounds={roundsByNumber(data.rounds)} />
        )}
      </Section>
    </section>
  );
}
