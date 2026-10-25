/**
 * The car's season at a glance: one cell per Grand Prix, marked with what its
 * power unit cost there.
 *
 * Server-safe: no state, no effects.
 */
import { ConsoleHeader, ConsolePanel } from "../../grand-prix/predictionConsole";
import { OVER_COLOR, PENDING_COLOR, type CarEvent, type RoundInfo } from "../powerUnitsModel";

interface Mark {
  text: string;
  color: string;
  filled: boolean;
  label: string;
}

function mark(event: CarEvent | undefined, round: RoundInfo, teamColor: string): Mark | null {
  if (!event) {
    return null;
  }
  const places = event.decisions.reduce(
    (sum, item) => sum + (item.outcome === "grid_drop" ? (item.places ?? 0) : 0),
    0,
  );
  if (event.decisions.some((item) => item.outcome === "pit_lane")) {
    return { text: "PL", color: OVER_COLOR, filled: true, label: `${round.name}: pit-lane start` };
  }
  if (places > 0) {
    return { text: `−${places}`, color: OVER_COLOR, filled: true, label: `${round.name}: ${places} grid places` };
  }
  if (event.penalty_status === "pending") {
    return { text: "?", color: PENDING_COLOR, filled: false, label: `${round.name}: stewards' decision pending` };
  }
  if (event.penalty_status === "not_found") {
    return { text: "!", color: PENDING_COLOR, filled: false, label: `${round.name}: no decision found` };
  }
  const units = event.new_parts.length;
  return { text: String(units), color: teamColor, filled: false, label: `${round.name}: ${units} new unit(s)` };
}

function Cell({
  round,
  event,
  teamColor,
  latest,
}: {
  round: RoundInfo;
  event?: CarEvent;
  teamColor: string;
  latest: boolean;
}) {
  const current = mark(event, round, teamColor);
  const body = (
    <>
      <span
        className={`font-mono text-[9px] font-bold uppercase tracking-[0.08em] ${round.has_documents ? "text-[#9AA1B0]" : "text-[#3A4354]"}`}
      >
        {round.code || `R${round.round}`}
      </span>
      <span
        className="mt-1 flex h-7 w-full items-center justify-center rounded font-mono text-[11px] font-black"
        style={
          current
            ? {
                background: current.filled ? current.color : `${current.color}1F`,
                color: current.filled ? "#FFFFFF" : current.color,
                boxShadow: `inset 0 0 0 1px ${current.color}`,
              }
            : { background: round.has_documents ? "#121825" : "transparent", color: "#3A4354" }
        }
      >
        {current?.text ?? "·"}
      </span>
    </>
  );
  const className = `flex w-11 shrink-0 flex-col items-center rounded px-0.5 py-1 ${latest ? "ring-1 ring-white/40" : ""}`;
  if (event) {
    return (
      <a
        href={`#round-${round.round}`}
        className={`${className} hover:bg-[#121825]`}
        aria-label={current?.label}
        title={current?.label}
      >
        {body}
      </a>
    );
  }
  return (
    <span className={className} title={`${round.name}: ${round.has_documents ? "nothing new" : "no documents yet"}`}>
      {body}
    </span>
  );
}

export function SeasonTimeline({
  rounds,
  events,
  teamColor,
  latestRound,
}: {
  rounds: RoundInfo[];
  events: CarEvent[];
  teamColor: string;
  latestRound: number | null;
}) {
  const byRound = new Map(events.map((item) => [item.round, item]));
  return (
    <ConsolePanel>
      <ConsoleHeader
        label="Season timeline"
        right={
          <span className="hidden font-mono text-[10px] uppercase tracking-[0.14em] text-[#7F8797] sm:inline">
            number = new units · −n = grid drop · PL = pit lane · ? = pending
          </span>
        }
      />
      <div className="overflow-x-auto">
        <ol className="flex min-w-max gap-1 p-3">
          {rounds.map((round) => (
            <li key={round.round}>
              <Cell
                round={round}
                event={byRound.get(round.round)}
                teamColor={teamColor}
                latest={round.round === latestRound}
              />
            </li>
          ))}
        </ol>
      </div>
    </ConsolePanel>
  );
}
