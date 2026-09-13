/**
 * Constructor livery colours, shared by every surface that tints by team.
 *
 * Deliberately free of the `"use client"` boundary and of any React import: this
 * table is read during server rendering as well as in the browser, and keeping
 * it in a component module would drag that module's client-only dependencies
 * (framer-motion, recharts) into the server graph.
 */
export const TEAM_COLORS: Record<string, string> = {
  "Red Bull Racing": "#3671C6",
  "Red Bull": "#3671C6",
  Mercedes: "#27F4D2",
  Ferrari: "#E8002D",
  McLaren: "#FF8000",
  "Aston Martin": "#229971",
  "Alpine F1 Team": "#FF87BC",
  Alpine: "#FF87BC",
  Williams: "#64C4FF",
  "RB F1 Team": "#6692FF",
  RB: "#6692FF",
  "Haas F1 Team": "#B6BABD",
  Haas: "#B6BABD",
  "Kick Sauber": "#52E252",
  Audi: "#FF0000",
  "Cadillac F1 Team": "#E0D4B8",
};

/** Fallback for teams with no livery entry — historical or newly entered. */
export const NEUTRAL_TEAM_COLOR = "#6B7280";

/**
 * Resolves a constructor name to its livery colour.
 *
 * Matches loosely in both directions because the same team arrives as
 * "Red Bull" from one endpoint and "Red Bull Racing" from another.
 */
export const getTeamColor = (team: string): string => {
  for (const [key, color] of Object.entries(TEAM_COLORS)) {
    if (team.includes(key) || key.includes(team)) return color;
  }
  return NEUTRAL_TEAM_COLOR;
};
