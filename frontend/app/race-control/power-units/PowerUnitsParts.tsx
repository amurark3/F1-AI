import { DriverName } from "@/app/ui/names/DriverName";

import { StateTag } from "../grand-prix/StateTag";

import type { PowerUnitCar, PowerUnitsResponse } from "./powerUnitsModel";

/**
 * The drivers who raced a car, by surname. A stand-in races under his own
 * number, so it shows beside his name: "Hadjar / Lawson #30".
 */
export function SeatNames({ car, year, tagShared = false }: { car: PowerUnitCar; year: number; tagShared?: boolean }) {
  return (
    <>
      {car.drivers.map((stint, index) => (
        <span key={stint.id}>
          {index > 0 && " / "}
          <DriverName variant="last" name={stint.name} code={stint.code} id={stint.id} year={year} />
          {stint.car_number !== car.car_number && (
            <span className="ml-1 font-mono text-[11px] font-medium text-rc-ink-3">#{stint.car_number}</span>
          )}
        </span>
      ))}
      {tagShared && car.drivers.length > 1 && (
        <span className="ml-2">
          <StateTag tone="blue">Shared seat</StateTag>
        </span>
      )}
    </>
  );
}

/** What a section says when the season's usage has not been collected. */
export function UnavailableNote({ data }: { data: PowerUnitsResponse }) {
  return (
    <p className="text-sm text-rc-ink-3">
      {data.reason ?? "Power-unit usage hasn't been collected for this season yet."}
    </p>
  );
}
