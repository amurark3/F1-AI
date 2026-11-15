import { DriverName } from "@/app/ui/names/DriverName";
import { PanelHeading } from "@/app/ui/PanelHeading";

import { Panel } from "../components/RaceControlPrimitives";

import { lastSlot, penaltyNote } from "./gridHelpers";

import type { StartingGridResponse } from "./gridModel";

/**
 * What the empty state may claim, which depends on what is known: "no penalties" is a
 * statement about a published grid sheet, not about a round whose sheet is missing.
 */
function emptyStateMessage(data?: StartingGridResponse): string {
  if (!data?.available) {
    return "Penalties are not known for this round yet. They are published with the starting grid, once qualifying has run.";
  }
  if (data.provisional) {
    return "Penalties cannot be listed yet. The official grid sheet is not in our dataset, so only the qualifying order is known.";
  }
  return "No grid penalties were applied for this round. Every driver starts from the slot they qualified in.";
}

/**
 * Every sanction on the grid, in the hub's words. The offence and its FIA document come with
 * the document feed; f1db records the places dropped and nothing more, so none is invented.
 */
export function GridPenalties({ data }: { data?: StartingGridResponse }) {
  const penalties = data?.penalties ?? [];
  const last = lastSlot(data?.grid ?? []);

  return (
    <Panel as="section" className="p-5">
      <PanelHeading eyebrow="Penalties applied" />
      {penalties.length === 0 ? (
        <p className="text-sm leading-relaxed text-rc-ink-3">{emptyStateMessage(data)}</p>
      ) : (
        <ul>
          {penalties.map((slot) => (
            <li
              key={slot.driver_code}
              className="grid grid-cols-[1fr_auto] items-baseline gap-x-3 border-b border-rc-line-soft py-2.5 text-sm"
            >
              <span className="text-rc-ink">
                <DriverName variant="full" code={slot.driver_code} name={slot.driver_name} />{" "}
                <span className="font-mono text-[11px] text-rc-ink-3">{slot.driver_code}</span>
              </span>
              <span className="text-right font-mono text-xs font-semibold text-rc-red-text">
                {penaltyNote(slot, last)}
              </span>
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}
