"use client";

import { use } from "react";

import type { SectionResult } from "@/app/ui/section/useSection";

import { findCar, type PowerUnitCar, type PowerUnitsResponse } from "../powerUnitsModel";
import { usePowerUnits } from "../usePowerUnits";

export interface CarSectionProps {
  year: number;
  /** The URL segment: a car number, or a seat id. */
  segment: string;
  /** The server render's payload, as a promise each section takes up behind its own boundary. */
  seed: Promise<PowerUnitsResponse | null>;
}

export interface CarSection {
  state: SectionResult<PowerUnitsResponse>;
  /** The payload, once loaded and collected. */
  data: PowerUnitsResponse | undefined;
  /** The car the segment names; undefined while loading, uncollected, or unknown. */
  car: PowerUnitCar | undefined;
  /** Whether a payload has loaded that lacks the car (uncollected, or no such car). */
  absent: boolean;
}

/** Every section of the car page reads the one payload through this. */
export function useCar({ year, segment, seed }: CarSectionProps): CarSection {
  const state = usePowerUnits(year, use(seed));
  const data = state.data?.available ? state.data : undefined;
  const car = data ? findCar(data.cars, segment) : undefined;
  return { state, data, car, absent: state.data !== undefined && car === undefined };
}
