/**
 * Animated weather glyphs: the sun's rays turn, clouds drift, rain and snow
 * fall, lightning strikes and stars twinkle at night.
 *
 * Pure SVG driven by CSS keyframes (see `globals.css`), so the glyphs render on
 * the server and need no JavaScript. Every animation sits behind `motion-safe:`,
 * so a reader who prefers reduced motion gets the same picture, standing still.
 */
import type { WeatherCondition } from "./weekendTypes";
import type { CSSProperties } from "react";

// CSS transforms on SVG need a box to turn about; fill-box is the shape itself.
const PIVOT = "origin-center [transform-box:fill-box]";
const SPIN = `motion-safe:animate-wx-spin ${PIVOT}`;
const DRIFT = "motion-safe:animate-wx-drift";
const FALL = "motion-safe:animate-wx-fall";
const SNOW = "motion-safe:animate-wx-snow";
const TWINKLE = `motion-safe:animate-wx-twinkle ${PIVOT}`;
const GLOW = `motion-safe:animate-wx-glow ${PIVOT}`;

const SUN = "#FFC93C";
const RAY = "#FFB020";
const MOON = "#E9E4CF";
const CLOUD_LIGHT = "#D5DDEA";
const CLOUD_DIM = "#97A3B8";
const CLOUD_DARK = "#5D6A80";
const DROP = "#4C8DFF";
const BOLT = "#FFF200";

const CLOUD_PATH = "M20 46H46A9 9 0 0 0 47 28A13 13 0 0 0 22 25A10.5 10.5 0 0 0 20 46Z";
const MOON_PATH = "M38 14A17 17 0 1 0 50 42A13 13 0 1 1 38 14Z";
const BOLT_POINTS = "35,40 28,52 33,52 30,62 41,47 36,47 39,40";
const RAY_ANGLES = [0, 45, 90, 135, 180, 225, 270, 315];

const delay = (seconds: number): CSSProperties => ({ animationDelay: `${seconds}s` });

function Sun({ cx, cy, r }: { cx: number; cy: number; r: number }) {
  return (
    <g>
      <circle cx={cx} cy={cy} r={r * 1.8} fill={SUN} opacity={0.16} className={GLOW} />
      <g className={SPIN}>
        {RAY_ANGLES.map((angle) => (
          <line
            key={angle}
            x1={cx}
            y1={cy - r - 3}
            x2={cx}
            y2={cy - r - 7}
            stroke={RAY}
            strokeWidth={2.5}
            strokeLinecap="round"
            transform={`rotate(${angle} ${cx} ${cy})`}
          />
        ))}
      </g>
      <circle cx={cx} cy={cy} r={r} fill={SUN} />
    </g>
  );
}

function Star({ x, y, wait }: { x: number; y: number; wait: number }) {
  return (
    <path
      d={`M${x} ${y - 3}L${x + 0.9} ${y - 0.9}L${x + 3} ${y}L${x + 0.9} ${y + 0.9}L${x} ${y + 3}L${x - 0.9} ${y + 0.9}L${x - 3} ${y}L${x - 0.9} ${y - 0.9}Z`}
      fill="#FFFFFF"
      className={TWINKLE}
      style={delay(wait)}
    />
  );
}

function Moon({ scale = 1 }: { scale?: number }) {
  return (
    <g transform={scale === 1 ? undefined : `translate(${32 * (1 - scale)} ${20 * (1 - scale)}) scale(${scale})`}>
      <path d={MOON_PATH} fill={MOON} />
      <Star x={52} y={16} wait={0} />
      <Star x={14} y={12} wait={0.9} />
      <Star x={56} y={30} wait={1.7} />
    </g>
  );
}

interface CloudProps {
  fill: string;
  /** An SVG transform placing the cloud; the drift animation runs inside it. */
  offset?: string;
  className?: string;
  dashed?: boolean;
}

function Cloud({ fill, offset = "", className = DRIFT, dashed = false }: CloudProps) {
  return (
    <g transform={offset || undefined}>
      <path
        d={CLOUD_PATH}
        fill={dashed ? "none" : fill}
        stroke={dashed ? fill : undefined}
        strokeWidth={dashed ? 2 : undefined}
        strokeDasharray={dashed ? "4 3" : undefined}
        className={className}
      />
    </g>
  );
}

function Drops({ count, light = false }: { count: number; light?: boolean }) {
  const xs = count === 3 ? [24, 33, 42] : [20, 27, 34, 41, 48];
  return (
    <g>
      {xs.map((x, index) => (
        <line
          key={x}
          x1={x}
          y1={50}
          x2={x - 2}
          y2={light ? 54 : 57}
          stroke={DROP}
          strokeWidth={light ? 2 : 2.5}
          strokeLinecap="round"
          className={FALL}
          style={delay(index * 0.22)}
        />
      ))}
    </g>
  );
}

function Flakes() {
  return (
    <g>
      {[20, 28, 36, 44].map((x, index) => (
        <circle key={x} cx={x} cy={52} r={1.9} fill="#EEF4FF" className={SNOW} style={delay(index * 0.7)} />
      ))}
    </g>
  );
}

function FogBands() {
  return (
    <g stroke={CLOUD_DIM} strokeWidth={3} strokeLinecap="round">
      <line x1={14} y1={51} x2={46} y2={51} className={DRIFT} />
      <line x1={20} y1={57} x2={52} y2={57} className={DRIFT} style={delay(1.2)} />
    </g>
  );
}

function Scene({ condition, night }: { condition: WeatherCondition; night: boolean }) {
  switch (condition) {
    case "clear":
      return night ? <Moon /> : <Sun cx={32} cy={32} r={11} />;
    case "partly_cloudy":
      return (
        <>
          {night ? <Moon scale={0.75} /> : <Sun cx={23} cy={22} r={8} />}
          <Cloud fill={CLOUD_LIGHT} offset="translate(6 6) scale(0.9)" />
        </>
      );
    case "cloudy":
      return (
        <>
          <Cloud fill={CLOUD_DIM} offset="translate(-8 -6) scale(0.8)" />
          <Cloud fill={CLOUD_LIGHT} offset="translate(2 2)" />
        </>
      );
    case "fog":
      return (
        <>
          <Cloud fill={CLOUD_DIM} offset="translate(0 -6)" />
          <FogBands />
        </>
      );
    case "drizzle":
      return (
        <>
          <Cloud fill={CLOUD_LIGHT} offset="translate(0 -6)" />
          <Drops count={3} light />
        </>
      );
    case "rain":
      return (
        <>
          <Cloud fill={CLOUD_DIM} offset="translate(0 -6)" />
          <Drops count={5} />
        </>
      );
    case "storm":
      return (
        <>
          <Cloud fill={CLOUD_DARK} offset="translate(0 -8)" />
          <polygon points={BOLT_POINTS} fill={BOLT} className="motion-safe:animate-wx-flash" />
          <Drops count={3} />
        </>
      );
    case "snow":
      return (
        <>
          <Cloud fill={CLOUD_LIGHT} offset="translate(0 -6)" />
          <Flakes />
        </>
      );
    default:
      return <Cloud fill={CLOUD_DIM} dashed className="" />;
  }
}

interface WeatherGlyphProps {
  condition: WeatherCondition;
  isDay: boolean | null;
  size?: number;
  /** Spoken label; omit when the condition is already written beside the glyph. */
  label?: string;
  className?: string;
}

export function WeatherGlyph({ condition, isDay, size = 64, label, className }: WeatherGlyphProps) {
  return (
    <svg
      viewBox="0 0 64 64"
      width={size}
      height={size}
      className={`overflow-visible ${className ?? ""}`}
      role={label ? "img" : undefined}
      aria-label={label}
      aria-hidden={label ? undefined : true}
    >
      <Scene condition={condition} night={isDay === false} />
    </svg>
  );
}
