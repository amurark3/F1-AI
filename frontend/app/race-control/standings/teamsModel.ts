/** Shared shapes and formatters for the championship hub (standings + team ops). */

import type { StandingsFreshness } from "@/app/lib/standingsFreshness";

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

export interface TeamsResponse extends StandingsFreshness {
  teams: Team[];
  drivers?: DriverStanding[];
  error?: string | null;
  source?: string;
  generated_at?: string;
}

export function formatPoints(points: number): string {
  return Number.isInteger(points) ? String(points) : points.toFixed(1);
}
