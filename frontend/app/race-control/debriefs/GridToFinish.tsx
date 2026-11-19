"use client";

import { useSeasonDirectory } from "@/app/race-control/profiles/EntityLinks";
import { PanelHeading } from "@/app/ui/PanelHeading";
import { SlopeChart } from "@/app/ui/SlopeChart";

import { gridTitle, slopeItems } from "./debriefModel";

import type { DebriefSummary } from "./debriefTypes";

const CARD = "rounded-md border border-rc-line bg-(--surface) p-5 sm:p-6";

/** Each car's grid slot against where it finished. */
export function GridToFinish({ summary }: { summary: DebriefSummary }) {
  const directory = useSeasonDirectory();
  if (!summary.grid.available) {
    return (
      <div className={CARD}>
        <PanelHeading eyebrow="Grid to finish" />
        <p className="text-sm text-rc-ink-3">
          The official starting grid isn&apos;t published yet, so places gained aren&apos;t counted.
        </p>
      </div>
    );
  }
  return (
    // The kit's sr-only table can run past a phone's edge; clip it here (ui/ is off limits to this task).
    <figure className={`${CARD} relative overflow-x-clip`}>
      <PanelHeading
        eyebrow="Grid to finish"
        title={gridTitle(summary, directory)}
        sub="Coloured = gained or lost three places or more · dashed = did not finish, not classified or disqualified · L = laps completed"
      />
      <SlopeChart
        items={slopeItems(summary)}
        label="Grid against finish"
        startLabel="Grid"
        endLabel="Finish"
        emphasis={3}
        nameHeader="Driver"
      />
    </figure>
  );
}
