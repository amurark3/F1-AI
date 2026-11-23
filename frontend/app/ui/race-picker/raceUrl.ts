/** The earliest season available from the race workspace's OpenF1 views. */
export const FIRST_RACE_SEASON = 2023;

export function readRaceYear(search: URLSearchParams, currentYear: number): number | null {
  const value = search.get("year");
  if (value === null || !/^\d{4}$/.test(value)) return null;
  const year = Number(value);
  return year >= FIRST_RACE_SEASON && year <= currentYear ? year : null;
}

export function raceQuery(round: number | null, year: number | null): URLSearchParams {
  const query = new URLSearchParams();
  if (round !== null) query.set("round", String(round));
  if (year !== null) query.set("year", String(year));
  return query;
}
