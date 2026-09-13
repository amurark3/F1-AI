/**
 * Three-letter round codes for the season accuracy strip.
 *
 * Keyed on the Grand Prix name rather than the circuit's city. City initials
 * collide badly — a single season can carry Montréal, Monte Carlo and Monza,
 * which all abbreviate to "MON", leaving three identical labels on a row of
 * clickable pills. The GP name is also the more reliable of the two fields:
 * FastF1's provisional 2026 schedule files the Bahrain Grand Prix under
 * "Kuala Lumpur", which the city scheme would render as "KUA".
 */

/** How many characters a derived code keeps. */
const CODE_LENGTH = 3;

/** Shown when a race name normalises to nothing at all. */
const UNKNOWN_CODE = "TBC";

/**
 * Overrides for names the derived code gets *wrong*, and only those — every
 * other race falls through to `deriveCode`, so this table stays short enough
 * to audit. Each entry carries the defect it fixes.
 */
const RACE_CODES = new Map<string, string>([
  // "JAP" is an ethnic slur.
  ["japanese", "JPN"],
  // Collides with the Australian Grand Prix, which also derives "AUS".
  ["austrian", "AUT"],
  // Derives "SPA", which reads as Spa-Francorchamps — a circuit racing on a
  // different round of the same season, under the Belgian Grand Prix ("BEL").
  ["spanish", "ESP"],
  // Derives "UNI".
  ["united states", "USA"],
  // Derives "EMI"; Imola is how the round is known, and it keeps the race
  // distinct from the Italian Grand Prix at Monza ("ITA").
  ["emilia romagna", "IMO"],
  // Derives "70T".
  ["70th anniversary", "ANV"],
]);

/**
 * Folds a race name to its lookup key: diacritics stripped so "São Paulo"
 * matches "sao paulo", the "Grand Prix" suffix dropped, and every run of
 * punctuation flattened to a single space.
 */
function normaliseRaceName(name: string): string {
  return name
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/\bgrand prix\b/g, "")
    .replace(/[^a-z0-9]+/g, " ")
    .trim();
}

/** First `CODE_LENGTH` characters of the normalised name, ignoring spaces. */
function deriveCode(key: string): string {
  const code = key.replace(/ /g, "").slice(0, CODE_LENGTH).toUpperCase();
  return code === "" ? UNKNOWN_CODE : code;
}

/**
 * Three-letter code for a Grand Prix, e.g. "Spanish Grand Prix" -> "ESP".
 *
 * Three letters is lossy under any scheme, so callers should pair the code
 * with the full race name in an accessible label.
 */
export function raceCode(name: string): string {
  const key = normaliseRaceName(name);
  return RACE_CODES.get(key) ?? deriveCode(key);
}
