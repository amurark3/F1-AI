"use client";

import { useMemo, useRef, useState } from "react";

import { LABEL_HALO_EM } from "@/app/ui/cornerLabels";

import { nearestIndex, trackLayout, viewBoxString } from "./trackMapGeometry";

import type { CornerMarker } from "./telemetryModel";
import type { MouseEvent } from "react";

export interface MapMarker {
  key: string;
  x: number;
  y: number;
  label: string;
  kind: "brake" | "top";
}

export interface TrackMapProps {
  x: number[];
  y: number[];
  /** Stroke colour of the segment that starts at each point. */
  colourAt: (index: number) => string;
  /** Whether the segment starting at a point is dashed (a second encoding beside colour). */
  dashedAt?: (index: number) => boolean;
  corners?: CornerMarker[];
  markers?: MapMarker[];
  /** Text for the point under the pointer. */
  readout: (index: number) => string;
  ariaLabel: string;
}

const MARKER_FILL = { brake: "#D95926", top: "#F0EFEC" } as const;
const SURFACE = "#0D111B";

/**
 * A lap drawn round the circuit, one short segment per sample so each can carry
 * its own colour. Hovering reads out the nearest sample.
 */
export function TrackMap({ x, y, colourAt, dashedAt, corners = [], markers = [], readout, ariaLabel }: TrackMapProps) {
  const svgRef = useRef<SVGSVGElement>(null);
  const [hover, setHover] = useState<number | null>(null);
  const { view, stroke, fontSize, labels } = useMemo(() => trackLayout(x, y, corners), [x, y, corners]);

  const onMove = (event: MouseEvent<SVGSVGElement>) => {
    const svg = svgRef.current;
    const matrix = svg?.getScreenCTM();
    if (!svg || !matrix) return;
    const point = new DOMPoint(event.clientX, event.clientY).matrixTransform(matrix.inverse());
    setHover(nearestIndex(x, y, { x: point.x, y: point.y }));
  };

  return (
    <div className="relative w-full">
      <svg
        ref={svgRef}
        viewBox={viewBoxString(view)}
        className="h-auto max-h-[560px] w-full"
        role="img"
        aria-label={ariaLabel}
        onMouseMove={onMove}
        onMouseLeave={() => {
          setHover(null);
        }}
      >
        {x.slice(0, -1).map((startX, index) => (
          <line
            key={index}
            x1={startX}
            y1={-y[index]}
            x2={x[index + 1]}
            y2={-y[index + 1]}
            stroke={colourAt(index)}
            strokeWidth={stroke}
            strokeLinecap="round"
            strokeDasharray={dashedAt?.(index) ? `${stroke * 1.2} ${stroke * 1.2}` : undefined}
          />
        ))}
        {labels.map((corner) => (
          <g key={corner.label}>
            {corner.leader && <line {...corner.leader} stroke="#3A4354" strokeWidth={stroke / 4} />}
            <text
              x={corner.x}
              y={corner.y}
              fontSize={fontSize}
              fill="#A8AFBF"
              stroke={SURFACE}
              strokeWidth={fontSize * LABEL_HALO_EM}
              strokeLinejoin="round"
              paintOrder="stroke"
              textAnchor="middle"
              dominantBaseline="central"
              fontFamily="var(--font-geist-mono, monospace)"
            >
              {corner.label}
            </text>
          </g>
        ))}
        {markers.map((marker) => (
          <circle
            key={marker.key}
            cx={marker.x}
            cy={-marker.y}
            r={stroke * 0.9}
            fill={MARKER_FILL[marker.kind]}
            stroke={SURFACE}
            strokeWidth={stroke / 3}
          >
            <title>{marker.label}</title>
          </circle>
        ))}
        {hover !== null && (
          <circle cx={x[hover]} cy={-y[hover]} r={stroke * 1.3} fill="none" stroke="#FFFFFF" strokeWidth={stroke / 3} />
        )}
      </svg>
      <p
        className="pointer-events-none absolute left-3 top-3 rounded border border-[#1E2633] bg-[#0A0E16]/90 px-2 py-1 font-mono text-[11px] text-neutral-200"
        aria-live="polite"
      >
        {hover === null ? "Hover the track for a reading" : readout(hover)}
      </p>
    </div>
  );
}

/** A horizontal key for a sequential colour scale. */
export function GradientLegend({
  colours,
  min,
  max,
  unit,
}: {
  colours: string[];
  min: number;
  max: number;
  unit: string;
}) {
  const gradient = `linear-gradient(90deg, ${colours.join(", ")})`;
  return (
    <div className="flex items-center gap-2 font-mono text-[11px] text-[#A8AFBF]">
      <span>
        {Math.round(min)} {unit}
      </span>
      <span className="h-2 w-40 rounded-full" style={{ background: gradient }} aria-hidden />
      <span>
        {Math.round(max)} {unit}
      </span>
    </div>
  );
}
