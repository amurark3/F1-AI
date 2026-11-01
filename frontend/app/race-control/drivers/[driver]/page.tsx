import { notFound } from "next/navigation";

import { getDirectory, getDriverProfile } from "@/app/lib/server/profiles";
import { currentSeason } from "@/app/lib/server/raceControl";

import { isDriverProfile } from "../../profiles/profilesModel";

import { DriverView } from "./DriverView";

import type { Metadata } from "next";

interface DriverPageProps {
  params: Promise<{ driver: string }>;
}

/** Carries power-unit usage, which the FIA updates through a race weekend. */
export const revalidate = 300;

/**
 * Prerender every driver who raced this season, by f1db driver id.
 *
 * `dynamicParams` stays on, so a stand-in called up mid-season still renders.
 */
export async function generateStaticParams(): Promise<Array<{ driver: string }>> {
  const directory = await getDirectory(currentSeason());
  return (directory?.drivers ?? []).map((driver) => ({ driver: driver.id }));
}

export async function generateMetadata({ params }: DriverPageProps): Promise<Metadata> {
  const { driver: driverId } = await params;
  const year = currentSeason();
  const profile = await getDriverProfile(year, driverId);
  if (!isDriverProfile(profile)) {
    return { title: "Teams & Drivers | F1 AI" };
  }
  const { driver } = profile;
  return {
    title: `${driver.name} — ${year} F1 Season | F1 AI`,
    description: `${driver.name}'s ${year} Formula 1 season with ${driver.team_name}: race wins, the result of every round, and the power-unit usage of the car they drive.`,
  };
}

export default async function DriverPage({ params }: DriverPageProps) {
  const { driver: driverId } = await params;
  const year = currentSeason();
  const profile = await getDriverProfile(year, driverId);

  // Only a backend that answered "not found" proves the URL wrong.
  if (profile?.status === "not_found") {
    notFound();
  }

  return <DriverView driverId={driverId} year={year} initial={profile} />;
}
