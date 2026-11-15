import { Legend } from "@/app/ui/Legend";
import { PanelHeading } from "@/app/ui/PanelHeading";

import { Panel } from "../components/RaceControlPrimitives";

import type { Codes } from "./headToHeadInsights";
import type { PairColours } from "./headToHeadModel";
import type { ReactNode } from "react";

/** One independent head-to-head card: its own kind, its own computed finding, its own chart. */
export function HeadToHeadCard({
  eyebrow,
  title,
  sub,
  wide = false,
  children,
}: {
  eyebrow: string;
  title: string;
  sub?: ReactNode;
  wide?: boolean;
  children: ReactNode;
}) {
  return (
    <Panel as="section" className={`p-5 ${wide ? "lg:col-span-2" : ""}`}>
      <PanelHeading as="h2" eyebrow={eyebrow} title={title} sub={sub} className="!mb-3" />
      {children}
    </Panel>
  );
}

/** Driver B is always drawn dashed, so the pair stays apart when team-mates share a colour. */
export function DriverLegend({ colours, codes }: { colours: PairColours; codes: Codes }) {
  return (
    <Legend
      className="mt-3.5"
      label="Drivers"
      items={[
        { label: codes.a, color: colours.a },
        { label: `${codes.b} (dashed)`, color: colours.b },
      ]}
    />
  );
}
