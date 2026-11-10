"use client";

import { useReducedMotion } from "framer-motion";
import { useId, useMemo } from "react";

import { useIsHydrated } from "@/app/components/LocalTime";

import { LABEL_HALO_EM } from "./cornerLabels";
import {
  CIRCUIT_TRACK,
  circuitCornerLabels,
  circuitLabelSizing,
  outlinePath,
  type CircuitMapData,
} from "./outlinePath";
import { f1, rc } from "./tokens";

/** Seconds the marker takes to lap the outline. */
const LAP_SECONDS = 9;
/** The comet's tail, as a fraction of the lap. */
const TAIL = 0.06;
/** Corner numbers appear once the outline has finished drawing. */
const LABELS_AFTER_SECONDS = 1.6;
/** A leader from an apex to a number set further out, in viewBox units. */
const LEADER_WIDTH = 2;

/**
 * The circuit, drawn: the outline traces itself in, a marker laps it, and the
 * corner numbers settle in once the line is complete.
 *
 * The outline arrives turned and scaled by the backend. Each corner number is
 * placed clear of the track and of the other numbers (`circuitCornerLabels`),
 * with a halo in the hero band's colour behind it and, when it had to move out
 * from its apex, a thin leader back. The lapping marker is SMIL, which ignores CSS
 * media queries, so it is left out entirely for a reader who prefers reduced
 * motion — and added only after hydration, because the server cannot know the
 * reader's preference and the first client render must match its HTML. The
 * draw-in and labels sit behind `motion-safe:` like every other animation.
 */
export function CircuitMap({ map, name }: { map: CircuitMapData; name: string }) {
  const hydrated = useIsHydrated();
  const reduceMotion = useReducedMotion();
  const lapping = hydrated && reduceMotion === false;
  const uid = useId().replace(/[^\w-]/g, "");
  const trackId = `track-${uid}`;
  const glowId = `glow-${uid}`;
  const path = outlinePath(map);
  const { fontSize } = circuitLabelSizing(map);
  const labels = useMemo(() => circuitCornerLabels(map), [map]);

  return (
    <svg viewBox={`0 0 ${map.width} ${map.height}`} className="h-full w-full" role="img" aria-label={`${name} layout`}>
      <defs>
        <filter id={glowId} x="-20%" y="-20%" width="140%" height="140%">
          <feGaussianBlur stdDeviation="12" />
        </filter>
      </defs>

      <path
        d={path}
        fill="none"
        stroke={f1.red}
        strokeOpacity={0.4}
        strokeWidth={CIRCUIT_TRACK.halo}
        strokeLinejoin="round"
        filter={`url(#${glowId})`}
      />
      <path d={path} fill="none" stroke="#1A2130" strokeWidth={CIRCUIT_TRACK.band} strokeLinejoin="round" />
      <path
        id={trackId}
        d={path}
        fill="none"
        stroke="#F4F6FA"
        strokeWidth={CIRCUIT_TRACK.line}
        strokeLinejoin="round"
        pathLength={1}
        strokeDasharray="1 1"
        className="motion-safe:animate-track-draw"
      />

      {lapping && (
        <g>
          <path
            d={path}
            fill="none"
            stroke={rc.redText}
            strokeWidth={8}
            strokeLinecap="round"
            strokeLinejoin="round"
            pathLength={1}
            strokeDasharray={`${TAIL} ${1 - TAIL}`}
          >
            <animate
              attributeName="stroke-dashoffset"
              from={1 + TAIL}
              to={TAIL}
              dur={`${LAP_SECONDS}s`}
              repeatCount="indefinite"
            />
          </path>
          <circle r={16} fill={rc.redText} opacity={0.5} filter={`url(#${glowId})`}>
            <animateMotion dur={`${LAP_SECONDS}s`} repeatCount="indefinite">
              <mpath href={`#${trackId}`} />
            </animateMotion>
          </circle>
          <circle r={8} fill="#FFFFFF" stroke={rc.redText} strokeWidth={4}>
            <animateMotion dur={`${LAP_SECONDS}s`} repeatCount="indefinite">
              <mpath href={`#${trackId}`} />
            </animateMotion>
          </circle>
        </g>
      )}

      <g fontFamily="var(--font-geist-mono, monospace)" fontWeight={700} fontSize={fontSize} textAnchor="middle">
        {labels.map((corner, index) => (
          <g
            key={corner.label}
            className="motion-safe:animate-fade-up"
            style={{ animationDelay: `${LABELS_AFTER_SECONDS + index * 0.05}s` }}
          >
            {corner.leader && (
              <line {...corner.leader} stroke={rc.dim} strokeWidth={LEADER_WIDTH} strokeLinecap="round" />
            )}
            <text
              x={corner.x}
              y={corner.y}
              dominantBaseline="central"
              fill={rc.ink3}
              stroke={rc.hero}
              strokeWidth={fontSize * LABEL_HALO_EM}
              strokeLinejoin="round"
              paintOrder="stroke"
            >
              {corner.label}
            </text>
          </g>
        ))}
      </g>
    </svg>
  );
}
