"use client";

import Link from "next/link";

import { getTeamColor } from "@/app/lib/teamColors";
import { driverLabel } from "@/app/ui/names/names";
import { Section } from "@/app/ui/section/Section";

import { carHref } from "../powerUnitsModel";

import { useCar, type CarSectionProps } from "./useCar";

const LINK =
  "flex-none inline-flex items-center gap-1.5 rounded border border-transparent px-2 py-1.5 font-mono text-[11px] font-semibold leading-none";

/** Every car of the season, one click apart, by number. */
export function CarStrip(props: CarSectionProps) {
  const { state, data, car } = useCar(props);
  const cars = [...(data?.cars ?? [])].sort((a, b) => a.car_number - b.car_number);
  return (
    <Section state={state} label="Cars" skeletonClassName="h-8" className="max-w-full">
      {cars.length > 0 && (
        <nav aria-label="Other cars" className="flex max-w-full gap-0.5 overflow-x-auto sm:flex-wrap">
          {cars.map((item) => {
            const who = `${driverLabel(item.driver, "full")} · ${item.team}`;
            const current = item.seat_id === car?.seat_id;
            return (
              <Link
                key={item.seat_id}
                href={carHref(item)}
                aria-current={current ? "page" : undefined}
                aria-label={`Car ${item.car_number} · ${who}`}
                title={who}
                className={`${LINK} ${current ? "border-rc-line bg-rc-raised text-rc-ink" : "text-rc-ink-3 hover:text-rc-ink"}`}
              >
                <i
                  aria-hidden="true"
                  className="h-3 w-[3px] rounded-[1px]"
                  style={{ backgroundColor: getTeamColor(item.team) }}
                />
                {item.car_number}
              </Link>
            );
          })}
        </nav>
      )}
    </Section>
  );
}
