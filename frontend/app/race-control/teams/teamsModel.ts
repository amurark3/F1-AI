/** Shared shapes and formatters for the championship hub (standings + team ops). */

export interface DriverStanding {
  code?: string;
  driver: string;
  team: string;
  points: number;
  position: number;
  wins: number;
}

export interface Team {
  slug: string;
  name: string;
  color: string;
  position: number;
  points: number;
  wins: number;
  drivers: DriverStanding[];
  strengths: string[];
  weaknesses: string[];
  standing_profile?: Record<string, number>;
  pace_profile?: Record<string, number>;
}

export interface TeamsResponse {
  teams: Team[];
  drivers?: DriverStanding[];
  error?: string | null;
  source?: string;
  generated_at?: string;
}

/** Three-letter tag for a driver, falling back to initials when the feed omits one. */
export function driverCode(driver: DriverStanding): string {
  return driver.code ?? driver.driver.slice(0, 3).toUpperCase();
}

export function formatPoints(points: number): string {
  return Number.isInteger(points) ? String(points) : points.toFixed(1);
}
