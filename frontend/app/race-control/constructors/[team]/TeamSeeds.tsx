import { notFound } from "next/navigation";

import { getDirectory, getTeamProfile } from "@/app/lib/server/profiles";

import { TeamSwitch } from "./TeamSwitch";
import { TeamView } from "./TeamView";

interface SeedProps {
  year: number;
  teamId: string;
}

/** Reads the directory on the server and hands it to the switch as its seed. */
export async function SeededTeamSwitch({ year, teamId }: SeedProps) {
  return <TeamSwitch year={year} teamId={teamId} seed={await getDirectory(year)} />;
}

/**
 * Reads the team's season on the server and hands it to the view as its seed.
 *
 * Only a backend that answered "not found" proves the URL wrong. With no
 * answer at all the browser fetches for itself and decides.
 */
export async function SeededTeamView({ year, teamId }: SeedProps) {
  const profile = await getTeamProfile(year, teamId);
  if (profile?.status === "not_found") {
    notFound();
  }
  return <TeamView year={year} teamId={teamId} seed={profile} />;
}
