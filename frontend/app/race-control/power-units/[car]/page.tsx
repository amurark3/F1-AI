import { currentSeason, getPowerUnits } from "@/app/lib/server/raceControl";
import { driverLabel, teamLabel } from "@/app/ui/names/names";

import { findCar, type PowerUnitsResponse } from "../powerUnitsModel";

import { CarView } from "./CarView";

import type { Metadata } from "next";

interface CarPageProps {
  params: Promise<{ car: string }>;
}

/** Documents arrive through a race weekend; the collection job runs hourly. */
export const revalidate = 300;

const FALLBACK_TITLE = "Power Unit Tracker | F1 AI";

/**
 * Prerender every car of the season, by its current number.
 *
 * `dynamicParams` stays on, so a number not on this list — a stand-in's own
 * number, or a car added mid-season — still renders on demand.
 */
export async function generateStaticParams(): Promise<Array<{ car: string }>> {
  const data = await getPowerUnits<PowerUnitsResponse>(currentSeason());
  return (data?.cars ?? []).map((car) => ({ car: String(car.car_number) }));
}

export async function generateMetadata({ params }: CarPageProps): Promise<Metadata> {
  const { car: segment } = await params;
  const data = await getPowerUnits<PowerUnitsResponse>(currentSeason());
  const car = data ? findCar(data.cars, segment) : undefined;
  if (!car) {
    // A loaded payload without the car proves the URL wrong; no payload proves nothing.
    return data?.available ? { title: FALLBACK_TITLE, robots: { index: false } } : { title: FALLBACK_TITLE };
  }
  const driver = driverLabel(car.driver, "full");
  const team = teamLabel({ id: car.team_id, name: car.team }, "name");
  return {
    title: `#${car.car_number} ${driver} — Power Units | F1 AI`,
    description: `${driver}'s ${team} power-unit allocation: every engine, turbo, MGU-K, energy store and more, the Grand Prix each arrived at, and the grid penalties they cost.`,
  };
}

/** Awaits only `params`: the payload goes to the sections as a promise, so no section waits for another. */
export default async function CarPage({ params }: CarPageProps) {
  const { car: segment } = await params;
  const year = currentSeason();
  return <CarView year={year} segment={segment} seed={getPowerUnits<PowerUnitsResponse>(year)} />;
}
