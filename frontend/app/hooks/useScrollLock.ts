"use client";

import { useEffect } from "react";

/**
 * Stops the page scrolling behind a full-screen overlay while `locked`, and
 * puts back whatever overflow the root had when it releases.
 */
export function useScrollLock(locked: boolean): void {
  useEffect(() => {
    if (!locked) return;
    const root = document.documentElement;
    const previous = root.style.overflow;
    root.style.overflow = "hidden";
    return () => {
      root.style.overflow = previous;
    };
  }, [locked]);
}
