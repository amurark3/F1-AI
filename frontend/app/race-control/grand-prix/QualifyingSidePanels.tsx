import { DriverName } from "@/app/ui/names/DriverName";
import { PanelHeading } from "@/app/ui/PanelHeading";

import { Panel } from "../components/RaceControlPrimitives";

import { partLeaders, stewardsCard, type PoleMargin } from "./qualifyingModel";

import type { QualifyingEntry } from "./sessionsModel";

function PoleMarginPanel({ margin }: { margin: PoleMargin }) {
  return (
    <Panel as="section" className="p-5">
      <PanelHeading eyebrow="Pole margin" />
      <p className="font-display text-[56px] font-extrabold leading-none text-rc-gold">
        {margin.seconds}
        <span className="ml-1 text-xl text-rc-ink-3">s</span>
      </p>
      <p className="mt-2 text-sm text-rc-ink-3">
        <DriverName variant="last" code={margin.pole.driver_code} name={margin.pole.driver_name} /> over{" "}
        <DriverName variant="last" code={margin.second.driver_code} name={margin.second.driver_name} />
      </p>
    </Panel>
  );
}

function PartLeadersPanel({ entries }: { entries: QualifyingEntry[] }) {
  return (
    <Panel as="section" className="p-5">
      <PanelHeading eyebrow="Fastest in each part" />
      {partLeaders(entries).map(({ label, entry }) => (
        <div
          key={label}
          className="grid grid-cols-[40px_1fr_auto] items-baseline border-b border-rc-line-soft py-2.5 text-sm"
        >
          <span className="font-mono text-[11px] text-rc-ink-3">{label}</span>
          <DriverName variant="full" code={entry.driver_code} name={entry.driver_name} />
          <span className="font-mono text-[13px] font-semibold text-(--f1-sector-best)">
            {entry[label.toLowerCase() as "q1" | "q2" | "q3"]}
          </span>
        </div>
      ))}
    </Panel>
  );
}

function StewardsPanel({ entries }: { entries: QualifyingEntry[] }) {
  const card = stewardsCard(entries);
  return (
    <Panel as="section" className="p-5">
      <PanelHeading eyebrow="Stewards" title={card.title} />
      <p className="text-[13px] leading-relaxed text-rc-ink-3">{card.body}</p>
    </Panel>
  );
}

/** Pole margin, the fastest lap of each part and the decisions that changed the order. */
export function QualifyingSidePanels({ entries, margin }: { entries: QualifyingEntry[]; margin: PoleMargin | null }) {
  return (
    <div className="space-y-4">
      {margin && <PoleMarginPanel margin={margin} />}
      <PartLeadersPanel entries={entries} />
      <StewardsPanel entries={entries} />
    </div>
  );
}
