/**
 * Tyre compound colours, matching the sidewall markings used on track.
 *
 * These are the colours a viewer already reads a stint chart with, so they are
 * not negotiable design choices — a yellow bar means medium to anyone who
 * watches the sport, whatever the rest of the palette does.
 */

const COMPOUND_COLORS: Record<string, string> = {
  SOFT: "#E8002D",
  MEDIUM: "#F5C542",
  HARD: "#E7E9EE",
  INTERMEDIATE: "#00A550",
  WET: "#3671C6",
  // Pre-2019 compound names still appear in historical data.
  SUPERSOFT: "#E8002D",
  ULTRASOFT: "#C64BC6",
  HYPERSOFT: "#FF8FA6",
  SUPERHARD: "#E7E9EE",
};

/** Shown for a stint whose compound was never recorded. */
export const UNKNOWN_COMPOUND_COLOR = "#4A5261";

/** Single-letter marker used inside a narrow stint bar. */
const COMPOUND_INITIALS: Record<string, string> = {
  SOFT: "S",
  MEDIUM: "M",
  HARD: "H",
  INTERMEDIATE: "I",
  WET: "W",
};

export function compoundColor(compound: string | null): string {
  if (!compound) return UNKNOWN_COMPOUND_COLOR;
  return COMPOUND_COLORS[compound.toUpperCase()] ?? UNKNOWN_COMPOUND_COLOR;
}

/** Compound initial, or "?" when the compound is unknown. */
export function compoundInitial(compound: string | null): string {
  if (!compound) return "?";
  const key = compound.toUpperCase();
  return COMPOUND_INITIALS[key] ?? key.charAt(0);
}

/** Readable compound name, title-cased, or an explicit unknown. */
export function compoundLabel(compound: string | null): string {
  if (!compound) return "Not recorded";
  const key = compound.toUpperCase();
  return key.charAt(0) + key.slice(1).toLowerCase();
}

/**
 * Text colour that stays readable on a compound's fill.
 *
 * Hard and intermediate are light enough that white text disappears on them.
 */
export function compoundTextColor(compound: string | null): string {
  const key = (compound ?? "").toUpperCase();
  return key === "HARD" || key === "SUPERHARD" ? "#0D111B" : "#FFFFFF";
}

/** The compounds present in a race, in the order they should be listed. */
export function compoundsUsed(compounds: Array<string | null>): string[] {
  const order = ["SOFT", "MEDIUM", "HARD", "INTERMEDIATE", "WET"];
  const seen = new Set(compounds.filter((c): c is string => Boolean(c)).map((c) => c.toUpperCase()));
  const known = order.filter((c) => seen.has(c));
  const extra = [...seen].filter((c) => !order.includes(c)).sort();
  return [...known, ...extra];
}
