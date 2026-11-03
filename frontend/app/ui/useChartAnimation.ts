import { useReducedMotion } from "framer-motion";
import { useEffect, useState } from "react";

import { useIsHydrated } from "@/app/components/LocalTime";

/** How long a chart takes to draw in: the kit's 1 s `grow-x` entrance. */
export const CHART_ENTRANCE_MS = 1000;
/** The kit's entrance curve (`--ease` in the mockups' system.css), in Recharts' spelling. */
export const CHART_EASING = "cubic-bezier(0.22,1,0.36,1)";

export interface ChartAnimationOptions {
  /** Milliseconds before this chart (or series) starts, to stagger several. */
  delayMs?: number;
  durationMs?: number;
}

/** Spread onto a Recharts series: `<Bar {...animation.series} />`. */
export interface ChartSeriesAnimation {
  isAnimationActive: boolean;
  animationBegin: number;
  animationDuration: number;
  animationEasing: typeof CHART_EASING;
}

export interface ChartAnimation {
  /** True while the entrance may play; hand-drawn SVG keys its entrance classes off it. */
  active: boolean;
  series: ChartSeriesAnimation;
}

/**
 * Entrance-only animation for a chart.
 *
 * The entrance plays once, when the chart first appears, and only for a
 * reader whose system reports no reduced-motion preference. Once it has had
 * time to finish, `active` turns false for good, so a later data change
 * redraws in place instead of replaying. Nothing animates before hydration:
 * the server cannot know the reader's preference, and the first client render
 * must match its HTML. Recharts charts inside `ResponsiveContainer` draw only
 * after mount, so they still get the entrance.
 */
export function useChartAnimation({
  delayMs = 0,
  durationMs = CHART_ENTRANCE_MS,
}: ChartAnimationOptions = {}): ChartAnimation {
  const hydrated = useIsHydrated();
  const reduceMotion = useReducedMotion();
  const motionAllowed = hydrated && reduceMotion === false;
  const [finished, setFinished] = useState(false);

  useEffect(() => {
    if (!motionAllowed || finished) return undefined;
    const timer = setTimeout(() => setFinished(true), delayMs + durationMs);
    return () => clearTimeout(timer);
  }, [motionAllowed, finished, delayMs, durationMs]);

  const active = motionAllowed && !finished;
  return {
    active,
    series: {
      isAnimationActive: active,
      animationBegin: delayMs,
      animationDuration: durationMs,
      animationEasing: CHART_EASING,
    },
  };
}
