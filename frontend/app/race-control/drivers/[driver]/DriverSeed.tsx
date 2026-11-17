import { notFound } from "next/navigation";

import { getDriverProfile } from "@/app/lib/server/profiles";

import { DriverView } from "./DriverView";

interface SeedProps {
  year: number;
  driverId: string;
}

/**
 * Reads the driver's season on the server and hands it to the view as its seed.
 *
 * Only a backend that answered "not found" proves the URL wrong. With no
 * answer at all the browser fetches for itself and decides.
 */
export async function SeededDriverView({ year, driverId }: SeedProps) {
  const profile = await getDriverProfile(year, driverId);
  if (profile?.status === "not_found") {
    notFound();
  }
  return <DriverView year={year} driverId={driverId} seed={profile} />;
}
