/**
 * The time left to a moment, split into the padded fields a countdown shows.
 * No React, so it reads the same on the server and in the browser.
 */

export interface CountdownParts {
  days: string;
  hours: string;
  minutes: string;
  seconds: string;
}

const pad = (value: number) => String(value).padStart(2, "0");

/** Days, hours, minutes and seconds from `nowMs` to `targetMs`; all "00" once it has passed. */
export function countdownParts(targetMs: number, nowMs: number): CountdownParts {
  const remaining = Math.max(0, Math.floor((targetMs - nowMs) / 1000));
  return {
    days: pad(Math.floor(remaining / 86_400)),
    hours: pad(Math.floor((remaining % 86_400) / 3600)),
    minutes: pad(Math.floor((remaining % 3600) / 60)),
    seconds: pad(remaining % 60),
  };
}
