"use client";

import { motion } from "framer-motion";

/**
 * A top-bar item (the mockups' `.nav a`): mono caps that fill the bar's
 * height, so the underline sits on the bar's bottom edge, over the red streak.
 * The bar is flush against the top of the viewport, which would clip the
 * focus ring, so the ring draws inside the item.
 */
export const NAV_ITEM =
  "relative flex h-full items-center font-mono text-[11px] font-medium uppercase leading-none tracking-[0.18em] transition-colors focus-visible:-outline-offset-2";

/** The current section reads in the primary tone; the rest wait in the label tone until hovered. */
export function navTone(current: boolean): string {
  return current ? "text-rc-ink" : "text-rc-ink-3 hover:text-rc-ink";
}

/** The mockups' `--ease`, for the underline's slide. */
const SLIDE = { type: "tween", ease: [0.22, 1, 0.36, 1], duration: 0.35 } as const;

/**
 * The red underline under the current section. One shared `layoutId`, so it
 * slides from the old section to the new one on navigation; the nav's
 * `MotionConfig reducedMotion="user"` makes it jump instead for readers who
 * ask for reduced motion.
 */
export function NavUnderline() {
  return (
    <motion.span
      layoutId="site-nav-underline"
      transition={SLIDE}
      aria-hidden="true"
      className="absolute inset-x-0 -bottom-px h-0.5 bg-f1-red"
    />
  );
}
