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
 * Overrides for names whose derived code is wrong or unconventional.
 *
 * There is no single rule in the sport: some rounds are known by their
 * country (Bahrain, Hungarian, Canadian), others by their circuit (Spa,
 * Monza, Suzuka, Imola). This table records the conventional short name for
 * each round that needs one. Most names already derive correctly — Miami,
 * Monaco, Barcelona, Mexico City, São Paulo, Las Vegas, Abu Dhabi — so only
 * the disagreements are listed, each with the reason it is listed.
 */
const RACE_CODES = new Map<string, string>([
  // --- Rounds known by circuit rather than country ----------------------
  // The country code would read as a translation of what these races are
  // actually called.
  ["belgian", "SPA"],
  // Monza cannot take "MON" — Monaco holds it — so it uses the timing-screen
  // form. This is also why the Emilia Romagna round is "IMO", not "EMI".
  ["italian", "MNZ"],
  ["emilia romagna", "IMO"],
  // Suzuka doubles as the fix for the derived "JAP", an ethnic slur. Do not
  // let this one fall back to `deriveCode`.
  ["japanese", "SUZ"],

  // --- Country codes where the derived form is wrong or unconventional ---
  // Collides with the Australian Grand Prix, which also derives "AUS".
  ["austrian", "AUT"],
  // The derived "CHI" / "BRI" / "DUT" / "FRE" are readable but are not what
  // a country-named round is called anywhere else in the sport.
  ["chinese", "CHN"],
  ["british", "GBR"],
  ["dutch", "NED"],
  ["french", "FRA"],
  // Derives "SPA", which belongs to Spa-Francorchamps above.
  ["spanish", "ESP"],
  // Derives "UNI".
  ["united states", "USA"],
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
