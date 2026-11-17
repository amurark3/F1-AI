import { Suspense } from "react";

import { getDirectory } from "@/app/lib/server/profiles";
import { currentSeason } from "@/app/lib/server/raceControl";
import { driverLabel, teamLabel } from "@/app/ui/names/names";

import { SeededDriverView } from "./DriverSeed";
import { DriverView } from "./DriverView";

import type { Metadata } from "next";

interface DriverPageProps {
  params: Promise<{ driver: string }>;
}

/** Follows the championship table, which moves once per race weekend. */
export const revalidate = 900;

/**
 * Prerender every driver who raced this season, by f1db driver id.
 *
 * `dynamicParams` stays on, so a stand-in called up mid-season still renders.
 */
export async function generateStaticParams(): Promise<Array<{ driver: string }>> {
  const directory = await getDirectory(currentSeason());
  return (directory?.drivers ?? []).map((driver) => ({ driver: driver.id }));
}

/** Reads only the directory, which the page and its static params share, so metadata never waits on the profile. */
export async function generateMetadata({ params }: DriverPageProps): Promise<Metadata> {
  const { driver: driverId } = await params;
  const year = currentSeason();
  const directory = await getDirectory(year);
  const driver = directory?.drivers.find((entry) => entry.id === driverId);
  if (!driver) {
    return { title: "F1 Drivers | F1 AI" };
  }
  const name = driverLabel(
    { name: driver.name, lastName: driver.last_name, code: driver.code, id: driver.id, year },
    "full",
  );
  const team = directory?.teams.find((entry) => entry.id === driver.team_id);
  const teamName = team ? teamLabel({ id: team.id, name: team.name, year }, "name") : "its team";
  return {
    title: `${name} — ${year} F1 Season | F1 AI`,
    description: `${name}'s ${year} Formula 1 season with ${teamName}: form, the result of every round, the teammate battle, points per race and power-unit usage from FIA documents.`,
  };
}

/** Nothing here waits on the backend: the section paints its skeleton at once and its seed streams in. */
export default async function DriverPage({ params }: DriverPageProps) {
  const { driver: driverId } = await params;
  const year = currentSeason();
  return (
    <Suspense fallback={<DriverView year={year} driverId={driverId} seed={null} />}>
      <SeededDriverView year={year} driverId={driverId} />
    </Suspense>
  );
}
