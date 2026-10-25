import { notFound } from "next/navigation";

import { currentSeason, getPowerUnits } from "@/app/lib/server/raceControl";

import { findCar, type PowerUnitsResponse } from "../powerUnitsModel";

import { CarView } from "./CarView";

import type { Metadata } from "next";

interface CarPageProps {
  params: Promise<{ car: string }>;
}

/** Documents arrive through a race weekend; the collection job runs hourly. */
export const revalidate = 300;

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
    return { title: "Power Unit Tracker | F1 AI" };
  }
  return {
    title: `#${car.car_number} ${car.driver.name} — Power Units | F1 AI`,
    description: `${car.driver.name}'s ${car.team} power-unit allocation: every engine, turbo, MGU-K, energy store and more, the Grand Prix each arrived at, and the grid penalties they cost.`,
  };
}

export default async function CarPage({ params }: CarPageProps) {
  const { car: segment } = await params;
  const year = currentSeason();
  const data = await getPowerUnits<PowerUnitsResponse>(year);
  // Only a payload that loaded and lacks the car proves the URL wrong; with no
  // payload at all the browser fetches it and decides.
  if (data?.available && !findCar(data.cars, segment)) {
    notFound();
  }
  return <CarView seed={{ year, data }} segment={segment} />;
}
