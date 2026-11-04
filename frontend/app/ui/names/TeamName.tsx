"use client";

import { directorySeason, useSeasonDirectory } from "@/app/race-control/profiles/EntityLinks";

import { teamLabel, type TeamIdentity, type TeamNameVariant } from "./names";

export interface TeamNameProps extends TeamIdentity {
  /** `name` (default) is f1db's name; `full` the full name, when the data has one. */
  variant?: TeamNameVariant;
  className?: string;
}

/** Whether this season's directory could say more than the payload does. */
function readsDirectory(team: TeamIdentity, variant: TeamNameVariant): boolean {
  const thisSeason = team.year === undefined || team.year === null || team.year === directorySeason();
  return thisSeason && (variant === "name" || !team.fullName?.trim());
}

/**
 * A team's canonical name: a feed's spelling ("Haas F1 Team") becomes f1db's
 * ("Haas") by exact name or alias in this season's directory; anything it
 * cannot place prints as the payload spells it.
 */
export function TeamName({ variant = "name", className, ...team }: TeamNameProps) {
  const directory = useSeasonDirectory(readsDirectory(team, variant));
  return <span className={className}>{teamLabel(team, variant, directory)}</span>;
}
