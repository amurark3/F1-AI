import type { DebriefRadio, RadioClip, RadioMomentKind } from "./debriefTypes";

const MS_PER_MINUTE = 60_000;
const CLOCK_START = 11;
const CLOCK_END = 19;
const MINUTES_PER_HOUR = 60;
const SECONDS_PER_MINUTE = 60;

export const MOMENT_TAG: Record<RadioMomentKind, string> = {
  start: "Start",
  safety_car: "Safety Car",
  safety_car_in: "Safety Car",
  vsc: "VSC",
  vsc_ending: "VSC",
  red_flag: "Red flag",
  chequered: "Flag",
  stop: "Stop",
  penalty: "Penalty",
  incident: "Incident",
  retirement: "DNF",
};

/** Titles of the race-wide moments; driver moments are titled in the component. */
export const RACE_TITLE: Partial<Record<RadioMomentKind, string>> = {
  start: "Formation lap and start",
  safety_car: "Safety Car deployed",
  safety_car_in: "Safety Car in",
  vsc: "Virtual Safety Car deployed",
  vsc_ending: "Virtual Safety Car ending",
  red_flag: "Red flag · race suspended",
  chequered: "Chequered flag",
};

function plural(count: number, noun: string): string {
  return `${count} ${noun}${count === 1 ? "" : "s"}`;
}

export function attachedCount(radio: DebriefRadio): number {
  return radio.moments.reduce((sum, moment) => sum + moment.clips.length, 0);
}

export function radioTitle(radio: DebriefRadio): string {
  return `${attachedCount(radio)} of ${plural(radio.total, "clip")} came within a lap of a race moment`;
}

/** The circuit's wall clock, read from the UTC string so server and client agree. */
export function circuitClock(at: string, offsetMinutes: number | null): string {
  return new Date(Date.parse(at) + (offsetMinutes ?? 0) * MS_PER_MINUTE).toISOString().slice(CLOCK_START, CLOCK_END);
}

export function offsetLabel(minutes: number): string {
  if (minutes === 0) return "UTC";
  const sign = minutes < 0 ? "−" : "+";
  const whole = Math.abs(minutes);
  const hours = Math.floor(whole / MINUTES_PER_HOUR);
  const rest = whole % MINUTES_PER_HOUR;
  return `UTC${sign}${hours}${rest ? `:${String(rest).padStart(2, "0")}` : ""}`;
}

export function timesNote(minutes: number | null): string {
  return minutes === null ? "times in UTC" : `times are local (${offsetLabel(minutes)})`;
}

export function clipCount(count: number): string {
  return plural(count, "clip");
}

export function moreSummary(count: number): string {
  return `${count} more ${count === 1 ? "clip" : "clips"}, not within a lap of a race moment`;
}

export function lapGroups(clips: RadioClip[]): Array<{ lap: number; clips: RadioClip[] }> {
  const groups = new Map<number, RadioClip[]>();
  for (const clip of clips) groups.set(clip.lap, [...(groups.get(clip.lap) ?? []), clip]);
  return [...groups].map(([lap, group]) => ({ lap, clips: group }));
}

export function playLabel(clip: RadioClip, offsetMinutes: number | null): string {
  const when = clip.lap === 0 ? "before the start" : `lap ${clip.lap}`;
  return `Play ${clip.driver_name} team radio, ${when}, ${circuitClock(clip.at, offsetMinutes)}`;
}

export function pauseLabel(clip: RadioClip): string {
  return `Pause ${clip.driver_name} team radio`;
}

export function mmss(seconds: number): string {
  const whole = Math.floor(seconds);
  return `${Math.floor(whole / SECONDS_PER_MINUTE)}:${String(whole % SECONDS_PER_MINUTE).padStart(2, "0")}`;
}
