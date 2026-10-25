/**
 * The "last updated" line every power-unit screen carries.
 *
 * Three moments, because they answer different questions: when fia.com was
 * last checked (is the collection running?), when that last changed anything
 * (when did the numbers last move?), and the newest FIA document read (how far
 * into the weekend do they reach?). A check more than a day old, or one that
 * failed, is said in words rather than left for the reader to work out.
 *
 * Server-safe: times are rendered in UTC, so server and browser agree.
 */
import {
  OVER_COLOR,
  PENDING_COLOR,
  formatUtc,
  type DocumentRef,
  type Freshness,
  type RoundInfo,
} from "./powerUnitsModel";

interface State {
  label: string;
  color: string;
}

function state(freshness: Freshness | null | undefined): State {
  if (!freshness?.checked_at) return { label: "Not checked yet", color: PENDING_COLOR };
  if (freshness.outcome === "aborted") return { label: "Last check failed", color: OVER_COLOR };
  if (freshness.outcome === "write_failed") return { label: "Last check not saved", color: OVER_COLOR };
  if (freshness.stale) return { label: "Collection overdue", color: PENDING_COLOR };
  if (freshness.outcome === "document_failures") return { label: "Some documents unread", color: PENDING_COLOR };
  return { label: "Up to date", color: "#00FF78" };
}

function Moment({ label, value }: { label: string; value: string }) {
  return (
    <span className="whitespace-nowrap">
      <span className="text-[#6F7789]">{label} </span>
      <span className="text-[#D7DBE3]">{value}</span>
    </span>
  );
}

export function FreshnessBar({
  freshness,
  asOf,
  rounds,
}: {
  freshness: Freshness | null | undefined;
  asOf: (DocumentRef & { round: number }) | null | undefined;
  rounds: Map<number, RoundInfo>;
}) {
  const current = state(freshness);
  const latestRound = asOf ? rounds.get(asOf.round) : undefined;
  return (
    <div
      role="status"
      className="mb-5 flex flex-wrap items-center gap-x-5 gap-y-1.5 rounded-md border border-[#1E2633] bg-[#0A0E16] px-3 py-2 font-mono text-[11px]"
    >
      <span
        className="inline-flex items-center gap-2 font-bold uppercase tracking-[0.16em]"
        style={{ color: current.color }}
      >
        <span className="relative flex h-2 w-2">
          <span
            className="absolute inline-flex h-full w-full animate-ping rounded-full opacity-40"
            style={{ background: current.color }}
          />
          <span className="relative inline-flex h-2 w-2 rounded-full" style={{ background: current.color }} />
        </span>
        {current.label}
      </span>
      <Moment label="Last checked" value={formatUtc(freshness?.checked_at)} />
      <Moment label="Last change" value={formatUtc(freshness?.changed_at)} />
      {asOf && (
        <Moment
          label="Latest FIA document"
          value={`${latestRound?.code ?? `R${asOf.round}`} · Doc ${asOf.number ?? "?"}`}
        />
      )}
      {freshness?.error && <span className="basis-full text-[#FFB4B1]">{freshness.error}</span>}
    </div>
  );
}
