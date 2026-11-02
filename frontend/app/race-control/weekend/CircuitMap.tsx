"use client";

import { useReducedMotion } from "framer-motion";
import { useId } from "react";

import { useIsHydrated } from "@/app/components/LocalTime";

import { outlinePath } from "./weekendModel";

import type { CircuitMapData } from "./weekendTypes";

/** Seconds the marker takes to lap the outline. */
const LAP_SECONDS = 9;
/** The comet's tail, as a fraction of the lap. */
const TAIL = 0.06;
/** Corner numbers appear once the outline has finished drawing. */
const LABELS_AFTER_SECONDS = 1.6;

/**
 * The circuit, drawn: the outline traces itself in, a marker laps it, and the
 * corner numbers settle in once the line is complete.
 *
 * The geometry arrives ready to draw — turned and scaled by the backend — so
 * this is presentation only. The lapping marker is SMIL, which ignores CSS
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
  const labelSize = Math.max(map.width, map.height) / 42;

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
        stroke="#E10600"
        strokeOpacity={0.4}
        strokeWidth={28}
        strokeLinejoin="round"
        filter={`url(#${glowId})`}
      />
      <path d={path} fill="none" stroke="#1A2130" strokeWidth={22} strokeLinejoin="round" />
      <path
        id={trackId}
        d={path}
        fill="none"
        stroke="#F4F6FA"
        strokeWidth={5}
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
            stroke="#FF4655"
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
          <circle r={16} fill="#FF4655" opacity={0.5} filter={`url(#${glowId})`}>
            <animateMotion dur={`${LAP_SECONDS}s`} repeatCount="indefinite">
              <mpath href={`#${trackId}`} />
            </animateMotion>
          </circle>
          <circle r={8} fill="#FFFFFF" stroke="#FF4655" strokeWidth={4}>
            <animateMotion dur={`${LAP_SECONDS}s`} repeatCount="indefinite">
              <mpath href={`#${trackId}`} />
            </animateMotion>
          </circle>
        </g>
      )}

      <g fontFamily="var(--font-geist-mono, monospace)" fontWeight={700} fontSize={labelSize} textAnchor="middle">
        {map.corners.map((corner, index) => (
          <text
            key={corner.label}
            x={corner.label_x}
            y={corner.label_y}
            dominantBaseline="central"
            fill="#7F8797"
            className="motion-safe:animate-fade-up"
            style={{ animationDelay: `${LABELS_AFTER_SECONDS + index * 0.05}s` }}
          >
            {corner.label}
          </text>
        ))}
      </g>
    </svg>
  );
}
