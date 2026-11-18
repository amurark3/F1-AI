"use client";

import { useSeasonDirectory } from "@/app/race-control/profiles/EntityLinks";
import { PanelHeading } from "@/app/ui/PanelHeading";
import { rc } from "@/app/ui/tokens";

import { isDecided, venueOf, type StandingsProgression } from "./standingsModel";
import { formatPoints } from "./teamsModel";
import { chartGeometry, FRAME, titleRaceSub, titleRaceTitle, type ChartGeometry } from "./titleRaceModel";

const CARD = "rounded-md border border-rc-line bg-(--surface) p-6";
const AXIS = { fontFamily: "var(--font-geist-mono)", fontSize: 10, fill: rc.ink3 } as const;
const LABEL = { fontFamily: "var(--font-geist-mono)", fontSize: 11, fontWeight: 600 } as const;

function Plot({ geometry }: { geometry: ChartGeometry }) {
  const { lines, ticks, marker } = geometry;
  return (
    <svg viewBox={`0 0 ${FRAME.width} ${FRAME.height}`} aria-hidden="true" className="h-auto w-full">
      {ticks.y.map((tick) => (
        <g key={tick.label}>
          <line x1={FRAME.left} x2={FRAME.right} y1={tick.y} y2={tick.y} stroke={rc.line} />
          <text x={FRAME.left - 8} y={tick.y + 3} textAnchor="end" style={AXIS}>
            {tick.label}
          </text>
        </g>
      ))}
      {ticks.x.map((tick) => (
        <text key={tick.label} x={tick.x} y={FRAME.height - 4} textAnchor="middle" style={AXIS}>
          {tick.label}
        </text>
      ))}
      {lines.map((line) => (
        <path
          key={line.key}
          d={line.d}
          pathLength={1}
          strokeDasharray="1 1"
          className="motion-safe:animate-track-draw"
          fill="none"
          stroke={line.color}
          strokeWidth={line.width}
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      ))}
      {lines.map((line) => (
        <text
          key={line.key}
          x={FRAME.labelX}
          y={line.labelY}
          style={{ ...LABEL, fill: line.quiet ? rc.ink2 : line.color }}
        >
          {line.label}
        </text>
      ))}
      {marker && (
        <>
          <circle cx={marker.cx} cy={marker.cy} r={5} fill={rc.gold} />
          <text
            x={marker.labelX}
            y={marker.labelY}
            textAnchor={marker.anchor}
            style={{ ...LABEL, fontSize: 10, fill: rc.gold }}
          >
            {marker.label}
          </text>
        </>
      )}
    </svg>
  );
}

/** The same numbers for a screen reader, since the drawing is hidden from it. */
function DataTable({ progression, title }: { progression: StandingsProgression; title: string }) {
  const { rounds, drivers } = progression;
  return (
    <div className="sr-only">
      <table>
        <caption>{title}</caption>
        <thead>
          <tr>
            <th scope="col">Driver</th>
            {rounds.map((r) => (
              <th key={r.round} scope="col">{`R${r.round}`}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {drivers.entrants.slice(0, 5).map((entrant) => (
            <tr key={entrant.key}>
              <th scope="row">{entrant.name}</th>
              {entrant.points.map((points, i) => (
                <td key={rounds[i].round}>{points === null ? "—" : formatPoints(points)}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** Cumulative points of the top five, round by round, with the round the title was won. */
export function TitleRaceChart({ progression }: { progression: StandingsProgression }) {
  const directory = useSeasonDirectory();
  const { rounds, drivers } = progression;
  const [leader] = drivers.entrants;

  if (rounds.length === 0 || !leader) {
    return (
      <figure className={CARD}>
        <PanelHeading eyebrow="Title race" sub="No round has paid points yet." />
      </figure>
    );
  }

  const geometry = chartGeometry(rounds, drivers.entrants, drivers.clinched);
  const title = titleRaceTitle(leader, rounds, isDecided("drivers", undefined, progression), directory);
  return (
    <figure className={CARD}>
      <PanelHeading eyebrow="Title race" title={title} sub={titleRaceSub(rounds, geometry.lines.length)} />
      <Plot geometry={geometry} />
      <DataTable progression={progression} title={title} />
      {drivers.clinched && (
        <p className="sr-only">{`Clinched after round ${drivers.clinched.round}, ${venueOf(rounds, drivers.clinched.round)}.`}</p>
      )}
    </figure>
  );
}
