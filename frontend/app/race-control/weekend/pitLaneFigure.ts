/**
 * The Key Numbers pit tile, read off the baseline plan: the latest same-circuit
 * edition's median pit-lane time (pit entry to pit exit, OpenF1), never a
 * modelled pit loss. With no figure the caption says why.
 */
import type { StrategyContext } from "../components/CommandCenterPanels";

export interface PitLaneFigure {
  seconds: number | null;
  detail: string;
}

export function pitLaneFigure(context: StrategyContext | undefined): PitLaneFigure {
  if (!context) return { seconds: null, detail: "Baseline plan unavailable" };
  const source = context.data_source;
  if (source?.mode !== "edition") return { seconds: null, detail: "No edition of this circuit measured" };
  const edition = `${source.edition_year} ${source.event_name ?? "edition"}`;
  const seconds = context.pit_model?.pit_lane_seconds ?? null;
  if (seconds === null) return { seconds, detail: `Not published for the ${edition}` };
  return { seconds, detail: `Median of ${context.pit_model?.pit_lane_stops ?? 0} stops · ${edition}` };
}
