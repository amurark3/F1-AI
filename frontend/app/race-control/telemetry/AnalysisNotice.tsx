import { InlineNotice, SectionLoader } from "../components/RaceControlPrimitives";

import type { AnalysisStatus } from "./telemetryModel";
import type { AnalysisData } from "./useAnalysisData";

const MODELED_LABELS: Record<string, string> = {
  distance: "distance along the lap (integrated from speed)",
  braking_zones: "braking zones",
  high_speed_zones: "high-speed stretches",
  corners: "corner positions (MultiViewer)",
  delta: "the time delta",
  mini_sectors: "mini-sector gains",
  corrected: "fuel-corrected lap times",
  fit: "the fitted wear rates",
  traffic: "the traffic flag",
  stint_boundaries: "stint boundaries snapped to pit-out laps",
};

/**
 * What to show instead of a chart: a loader, the backend's own reason, or a
 * fetch failure. Returns null when the answer is available and should render.
 */
export function AnalysisGate<T extends AnalysisStatus>({
  state,
  loadingTitle,
}: {
  state: AnalysisData<T>;
  loadingTitle: string;
}) {
  if (state.loading) {
    return <SectionLoader title={loadingTitle} detail="Reading lap and car data from OpenF1." />;
  }
  if (state.error) {
    return (
      <InlineNotice title="Could not load" tone="error">
        The analysis service did not answer. Try again shortly.
      </InlineNotice>
    );
  }
  const data = state.data;
  if (!data || data.available) return null;
  if (data.pending) {
    return <SectionLoader title={loadingTitle} detail={data.message ?? "Still loading from OpenF1."} />;
  }
  const tone = data.reason === "error" || data.reason === "openf1_unavailable" ? "error" : "warning";
  const title = data.reason === "openf1_live" ? "OpenF1 is closed during live sessions" : "Nothing to show";
  return (
    <InlineNotice title={title} tone={tone}>
      {data.message}
      {data.error_id && <span className="ml-1 font-mono text-xs text-neutral-400">(ref {data.error_id})</span>}
    </InlineNotice>
  );
}

/** The figures on this view that are modelled from measurements, not measured. */
export function ModeledNote({ modeled, extra }: { modeled?: string[]; extra?: string }) {
  if (!modeled?.length) return null;
  const items = modeled.map((key) => MODELED_LABELS[key] ?? key);
  return (
    <p className="text-xs leading-relaxed text-[#8E96A8]">
      <span className="mr-1.5 rounded border border-[#F5C542]/40 px-1.5 py-0.5 font-mono text-[10px] font-bold uppercase tracking-[0.14em] text-[#F5C542]">
        Modelled
      </span>
      {items.join(", ")} are derived from OpenF1&apos;s measured samples, not published by F1.
      {extra && ` ${extra}`}
    </p>
  );
}

export function AnalysisWarnings({ warnings }: { warnings?: string[] }) {
  if (!warnings?.length) return null;
  return (
    <InlineNotice title="Read with care" tone="warning">
      <ul className="list-disc space-y-0.5 pl-4">
        {warnings.map((warning) => (
          <li key={warning}>{warning}</li>
        ))}
      </ul>
    </InlineNotice>
  );
}
