"use client";

import { animate, motion, useMotionValue, useReducedMotion, useTransform } from "framer-motion";
import { useEffect } from "react";

interface AnimatedNumberProps {
  value: number;
  /** Digits after the decimal point. */
  decimals?: number;
  /** Seconds the count takes. */
  duration?: number;
  className?: string;
}

/**
 * A number that counts up from zero when it first appears.
 *
 * The server renders the final value, so the figure is right before hydration
 * and for readers without JavaScript. The count runs on a motion value, which
 * updates the text without re-rendering React, and is skipped entirely for a
 * reader who prefers reduced motion.
 */
export function AnimatedNumber({ value, decimals = 0, duration = 1.1, className }: AnimatedNumberProps) {
  const reduceMotion = useReducedMotion();
  const count = useMotionValue(value);
  const text = useTransform(count, (latest) => latest.toFixed(decimals));

  useEffect(() => {
    if (reduceMotion) {
      count.set(value);
      return undefined;
    }
    const controls = animate(count, value, { from: 0, duration, ease: [0.22, 1, 0.36, 1] });
    return () => controls.stop();
  }, [count, value, duration, reduceMotion]);

  return <motion.span className={className}>{text}</motion.span>;
}
