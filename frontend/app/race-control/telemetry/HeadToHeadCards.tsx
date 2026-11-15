"use client";

import { useMemo } from "react";

import { Legend } from "@/app/ui/Legend";

import { HeadToHeadCard } from "./HeadToHeadCard";
import { type Codes, lapTitle, mapTitle } from "./headToHeadInsights";
import { gainLabel, miniSectorAt, winnerColour, type PairColours } from "./headToHeadModel";
import { formatLapTime } from "./telemetryModel";
import { TrackMap } from "./TrackMap";
import { EVEN_COLOUR } from "./trackMapGeometry";

import type { ComparisonResponse, Stretch } from "./telemetryModel";

interface CardProps {
  data: ComparisonResponse;
  colours: PairColours;
  codes: Codes;
}

/** Each driver's lap, then each sector with its winner. */
export function LapCard({ data, colours, codes }: CardProps) {
  const sectors = data.sectors ?? [];
  return (
    <HeadToHeadCard
      wide
      eyebrow="Lap"
      title={lapTitle(data.gap, codes)}
      sub={`${codes.a} ${formatLapTime(data.a?.lap.time)} · ${codes.b} ${formatLapTime(data.b?.lap.time)} · best counted laps`}
    >
      <div className="grid gap-3 sm:grid-cols-3">
        {sectors.map((sector) => {
          const gain = sector.gain;
          return (
            <div key={sector.sector} className="rounded border border-rc-line-soft px-3 py-2.5">
              <p className="font-mono text-[11px] font-semibold uppercase tracking-[0.22em] text-rc-ink-3">
                Sector {sector.sector}
              </p>
              <p className="mt-2 font-display text-[32px] font-extrabold leading-none" style={{ color: colours.a }}>
                {formatLapTime(sector.a)}
              </p>
              <p className="mt-1 font-display text-xl font-bold leading-none" style={{ color: colours.b }}>
                {formatLapTime(sector.b)}
              </p>
              <p className="mt-2 font-mono text-xs text-rc-ink-2">
                {gain === null || gain === 0 ? (
                  "level"
                ) : (
                  <span style={{ color: winnerColour(gain > 0 ? "a" : "b", colours) }}>
                    {gain > 0 ? codes.a : codes.b} +{Math.abs(gain).toFixed(3)}
                  </span>
                )}
              </p>
            </div>
          );
        })}
      </div>
    </HeadToHeadCard>
  );
}

/** The circuit coloured by who was faster through each mini-sector. */
export function MiniSectorCard({ data, colours, codes }: CardProps) {
  const map = data.map;
  const stretches = useMemo(() => data.mini_sectors ?? [], [data.mini_sectors]);
  const owner = useMemo(() => miniSectorAt(stretches, map?.distance ?? []), [stretches, map]);
  if (!map) return null;
  const at = (index: number) => stretches[owner[index]] as Stretch | undefined;
  return (
    <HeadToHeadCard
      eyebrow="Mini-sectors"
      title={mapTitle(stretches, codes)}
      sub="Solid where the first driver was faster, dashed where the second was"
    >
      <TrackMap
        x={map.x}
        y={map.y}
        colourAt={(index) => winnerColour(at(index)?.faster ?? "even", colours)}
        dashedAt={(index) => at(index)?.faster === "b"}
        corners={data.corner_markers}
        readout={(index) => {
          const stretch = at(index);
          return `${Math.round(map.distance[index])} m · ${stretch ? `${stretch.label} · ${gainLabel(stretch, codes)}` : "-"}`;
        }}
        ariaLabel={`Circuit coloured by who was faster in each of ${stretches.length} mini-sectors`}
      />
      <Legend
        className="mt-3.5"
        label="Mini-sector winner"
        items={[
          { label: `${codes.a} faster`, color: colours.a },
          { label: `${codes.b} faster (dashed)`, color: colours.b },
          { label: "even", color: EVEN_COLOUR },
        ]}
      />
    </HeadToHeadCard>
  );
}
