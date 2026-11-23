"use client";

import { useReducedMotion } from "framer-motion";
import { useCallback, useEffect, useRef, useState } from "react";

export const PLAY_STEP_MS = 600;
export const PLAY_STEP_REDUCED_MS = 1500;

export interface Playback {
  playing: boolean;
  /** Plays on from the current step; at the last step it restarts from the grid. */
  toggle: () => void;
  pause: () => void;
}

/** Steps the replay forward on a timer, to `max`; `onStep` receives each new step. */
export function usePlayback(step: number, max: number, onStep: (step: number) => void): Playback {
  const [playing, setPlaying] = useState(false);
  const reduced = useReducedMotion();
  const latest = useRef(step);

  useEffect(() => {
    latest.current = step;
  }, [step]);

  useEffect(() => {
    if (!playing) return undefined;
    const id = setInterval(
      () => {
        const next = latest.current + 1;
        latest.current = next;
        onStep(next);
        if (next >= max) setPlaying(false);
      },
      reduced ? PLAY_STEP_REDUCED_MS : PLAY_STEP_MS,
    );
    return () => clearInterval(id);
  }, [playing, max, onStep, reduced]);

  const toggle = useCallback(() => {
    if (playing) return setPlaying(false);
    if (step >= max) onStep(0);
    return setPlaying(true);
  }, [playing, step, max, onStep]);

  const pause = useCallback(() => setPlaying(false), []);
  return { playing, toggle, pause };
}
