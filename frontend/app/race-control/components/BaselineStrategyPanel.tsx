/**
 * The Command Center's "Base race plan": the latest same-circuit edition's measured strategy.
 *
 * Every figure comes from that edition (OpenF1 stints, the published pit sheet,
 * OpenF1 pit-lane times), and the panel names the edition, its year and whether
 * it raced under the previous regulations. Nothing is modelled: until P0b.4 the
 * panel showed an undercut of 1.4 s, an overcut of 0.9 s and a traffic grade,
 * all formulas; nothing measures them, so they are not shown.
 *
 * No client boundary: a pure function of its props.
 */
import { PanelHeading } from "@/app/ui/PanelHeading";
import { StatTile, StatTiles } from "@/app/ui/StatTile";
import { EYEBROW } from "@/app/ui/typography";

import { StateTag } from "../grand-prix/StateTag";
import { compoundColor } from "../grand-prix/tyreCompounds";

import { Panel } from "./RaceControlPrimitives";

import type { StrategyContext, StrategyPlan, StrategySource } from "./CommandCenterPanels";

const NO_CONTEXT = "The baseline plan has not arrived yet.";

const stopsLabel = (stops: number): string => `${stops} stop${stops === 1 ? "" : "s"}`;

/** The headline sequence across the edition's laps, one band per stint, split on the median stop laps. */
function SequenceTimeline({ plan }: { plan: StrategyPlan }) {
  const laps = Math.max(plan.total_laps, 1);
  const share = (lap: number) => Math.min(100, Math.max(0, (lap / laps) * 100));
  const stops = plan.stints.slice(0, -1);

  return (
    <div>
      <div className="mb-4 flex items-center gap-3">
        <p className={EYEBROW}>Stint plan</p>
        <span className="h-px flex-1 bg-rc-line" />
        <p className="font-mono text-[10px] text-rc-ink-3">
          {plan.drivers.length} of {plan.finishers} finishers ran it
        </p>
      </div>

      <div className="relative mb-1.5 h-5">
        {stops.map((stint) => (
          <div
            key={`flag-${stint.end_lap}`}
            className="absolute -translate-x-1/2 whitespace-nowrap"
            style={{ left: `${share(stint.end_lap)}%` }}
          >
            <span className="font-mono text-[10px] font-semibold text-rc-ink-2">L{stint.end_lap}</span>
          </div>
        ))}
      </div>

      <div className="relative h-12 w-full overflow-hidden rounded border border-rc-line">
        {plan.stints.map((stint, index) => {
          const color = compoundColor(stint.compound);
          const left = share(stint.start_lap - 1);
          return (
            <div
              key={`stint-${stint.start_lap}`}
              data-stint={stint.compound}
              className="absolute inset-y-0 flex origin-left items-center overflow-hidden motion-safe:animate-fill-x"
              style={{
                left: `${left}%`,
                width: `${share(stint.end_lap) - left}%`,
                background: `${color}1F`,
                animationDelay: `${index * 0.25}s`,
              }}
            >
              <span className="truncate px-3 text-[11px] font-bold uppercase tracking-wide" style={{ color }}>
                {stint.compound}
              </span>
            </div>
          );
        })}
        {stops.map((stint) => (
          <div
            key={`stop-${stint.end_lap}`}
            className="absolute inset-y-0 w-[2px] bg-rc-ink"
            style={{ left: `${share(stint.end_lap)}%` }}
          />
        ))}
      </div>

      <div className="mt-2 flex items-start justify-between gap-3 font-mono text-[10px] text-rc-ink-3">
        <span>L1</span>
        <span className="text-center">Stops on the median lap of the finishers who ran it</span>
        <span>L{laps}</span>
      </div>
    </div>
  );
}

/** Which edition the plan is read from, and from which feeds. */
function PlanSource({ source }: { source: StrategySource }) {
  const edition = [
    `${source.edition_year} ${source.event_name ?? "edition"}`,
    source.previous_regulations ? "previous regulations" : null,
    `${source.sample_size ?? 0} finishers`,
  ]
    .filter(Boolean)
    .join(" · ");
  const sources = source.sources ?? [];
  return (
    <p className="mt-3.5 font-mono text-[10px] uppercase leading-[1.6] tracking-[0.1em] text-rc-ink-3">
      {edition}
      {sources.length > 0 && (
        <>
          <br />
          {sources.join(" · ")}
        </>
      )}
    </p>
  );
}

/** The measured figures under the plan: pit-lane time, stops, first stop, sample. */
function MeasuredGrid({ context, source }: { context: StrategyContext; source: StrategySource }) {
  const pitLane = context.pit_model?.pit_lane_seconds ?? null;
  const pitStops = context.pit_model?.pit_lane_stops ?? 0;
  const top = context.stop_counts?.[0];
  const first = context.first_stop;
  const finishers = source.sample_size ?? 0;
  return (
    <div className="mb-3.5 mt-6">
      <div className="mb-3.5 flex items-center gap-3">
        <p className={EYEBROW}>Measured in {source.edition_year}</p>
        <span className="h-px flex-1 bg-rc-line" />
      </div>
      <StatTiles>
        <StatTile
          label="Pit lane"
          value={pitLane ?? "—"}
          unit={pitLane === null ? undefined : "s"}
          sub={pitLane === null ? "Not published" : `Median of ${pitStops} stops, entry to exit`}
        />
        <StatTile
          label="Stops"
          value={top ? String(top.stops) : "—"}
          sub={top ? `${top.drivers} of ${finishers} finishers` : "Not published"}
        />
        <StatTile
          label="First stop"
          value={first ? `L${first.median_lap}` : "—"}
          sub={first ? `Middle half L${first.p25_lap}–L${first.p75_lap}` : "No finisher stopped"}
        />
        <StatTile label="Sample" value={String(finishers)} sub="Classified finishers" />
      </StatTiles>
    </div>
  );
}

/** The title, the confidence grade and what it rests on. */
function PlanHeader({ call }: { call: StrategyContext["primary_call"] | undefined }) {
  const confidence = call?.confidence ?? null;
  return (
    <PanelHeading
      as="h2"
      eyebrow="Baseline strategy"
      title={call?.title ?? "Base race plan"}
      sub={call?.confidence_basis ?? undefined}
      aside={
        <StateTag tone={confidence === "high" ? "blue" : "neutral"}>
          {confidence ? `${confidence} confidence` : "no plan"}
        </StateTag>
      }
    />
  );
}

/** The sequences the finishers ran besides the headline one. */
function Alternatives({ items }: { items: NonNullable<StrategyContext["alternatives"]> }) {
  if (items.length === 0) return null;
  return (
    <p className="mt-3 text-xs text-rc-ink-3">
      Also run:{" "}
      {items.map((item) => `${item.compounds.join("–")}, ${stopsLabel(item.stops)} (${item.drivers})`).join(" · ")}
    </p>
  );
}

export function BaselineStrategyPanel({ context }: { context: StrategyContext | undefined }) {
  const source = context?.data_source;
  const measured = source?.mode === "edition" ? source : null;
  const plan = context?.plan;

  return (
    <Panel className="h-full p-5 sm:p-6">
      <PlanHeader call={context?.primary_call} />

      {context?.rain_branch && (
        <p
          role="note"
          className="mb-4 rounded-lg border border-rc-line border-l-2 border-l-rc-blue bg-white/[0.03] px-3 py-2 text-sm text-rc-ink"
        >
          {context.rain_branch.note}
        </p>
      )}

      <p className="max-w-[70ch] text-[15px] leading-relaxed text-rc-ink-2">
        {context?.primary_call.summary ?? NO_CONTEXT}
      </p>

      {measured && <PlanSource source={measured} />}

      {plan && plan.stints.length > 0 && (
        <div className="mt-6">
          <SequenceTimeline plan={plan} />
        </div>
      )}

      <Alternatives items={context?.alternatives ?? []} />

      {context && measured && <MeasuredGrid context={context} source={measured} />}
    </Panel>
  );
}
