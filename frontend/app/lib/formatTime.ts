/**
 * Timestamp formatting shared by server and client renders.
 *
 * Every formatter takes an explicit locale and time zone. That is the whole
 * point: `Intl.DateTimeFormat(undefined, …)` resolves against whatever host it
 * runs on, so a server render bakes the *build machine's* zone into the HTML —
 * "04:30 AM PDT" served to a reader in Madrid. Pinning both arguments makes a
 * server render deterministic, and `LocalTime` swaps to the viewer's real zone
 * once it is mounted and can actually know it.
 */

/** Named presets, so a format is described by intent rather than by options. */
export type TimeStyle = "weekday" | "day" | "dayShort" | "time" | "stamp" | "stampZone";

const STYLES: Record<TimeStyle, Intl.DateTimeFormatOptions> = {
  /** "Fri, Sep 11" — session cards on the weekend clock. */
  weekday: { weekday: "short", month: "short", day: "numeric" },
  /** "Sep 11, 2026" — race dates in the prediction console. */
  day: { month: "short", day: "numeric", year: "numeric" },
  /** "Sep 11" — round tiles in the season selector, where width is scarce. */
  dayShort: { month: "short", day: "2-digit" },
  /** "04:30 AM PDT" — session start times. */
  time: { hour: "2-digit", minute: "2-digit", timeZoneName: "short" },
  /** "Sep 11, 04:30 AM" — snapshot timestamps. */
  stamp: { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" },
  /** "Sep 11, 04:30 AM PDT" — feed refresh times, where the zone matters. */
  stampZone: { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", timeZoneName: "short" },
};

/**
 * The locale used for server renders.
 *
 * Fixed rather than host-resolved for the same reason as the time zone: Node's
 * default locale is not the reader's, and letting it vary would make the
 * prerendered HTML differ from the browser's first render.
 */
const SERVER_LOCALE = "en-US";

/** Where a timestamp is being read from. Undefined means "ask the host". */
interface Where {
  locale?: string;
  timeZone?: string;
}

/** Formats a timestamp in UTC — identical output on any host. */
export function formatUtc(value: string | undefined | null, style: TimeStyle, fallback: string): string {
  return formatIn(value, style, fallback, { locale: SERVER_LOCALE, timeZone: "UTC" });
}

/** Formats a timestamp in the viewer's own locale and zone. Browser only. */
export function formatLocal(value: string | undefined | null, style: TimeStyle, fallback: string): string {
  return formatIn(value, style, fallback, {});
}

function formatIn(value: string | undefined | null, style: TimeStyle, fallback: string, where: Where): string {
  if (!value) return fallback;

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return fallback;

  return new Intl.DateTimeFormat(where.locale, {
    ...STYLES[style],
    ...(where.timeZone ? { timeZone: where.timeZone } : {}),
  }).format(date);
}

/** The viewer's IANA zone, or "UTC" on a host that has no viewer. */
export function resolvedTimeZone(): string {
  return Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
}
