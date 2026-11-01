"use client";

import { ExternalLink } from "lucide-react";
import Link from "next/link";
import useSWR from "swr";

import { API_BASE } from "@/app/constants/api";
import { fetcher } from "@/app/utils/fetcher";

import { outcomeLabel, type Decision, type DriverRef } from "../power-units/powerUnitsModel";
import { DriverLink, TeamLink } from "../profiles/EntityLinks";

import { ConsoleHeader, ConsolePanel, InfoRow } from "./predictionConsole";

interface Headliner {
  driver_id: string;
  driver_name: string;
  team_id: string;
  team_name: string;
}

interface GlanceDecision extends Decision {
  car_number: number;
  team: string;
  team_id: string;
  driver: DriverRef;
}

/** `GET /api/race-control/glance/{year}/{round}` */
interface RaceGlance {
  previous: { year: number; round: number; name: string; winner: Headliner | null; pole: Headliner | null } | null;
  power_units: { available: boolean; reason: string | null; decisions: GlanceDecision[] };
}

function HeadlinerValue({ person }: { person: Headliner | null }) {
  if (!person) return <>-</>;
  return (
    <>
      <DriverLink id={person.driver_id}>{person.driver_name}</DriverLink>{" "}
      <span className="font-normal text-[#6F7789]">
        (<TeamLink id={person.team_id}>{person.team_name}</TeamLink>)
      </span>
    </>
  );
}

function PenaltyList({ section }: { section: RaceGlance["power_units"] }) {
  if (!section.available) {
    return <p className="pt-3 text-xs text-[#6F7789]">{section.reason ?? "Power-unit decisions are not available."}</p>;
  }
  if (section.decisions.length === 0) {
    return <p className="pt-3 text-xs text-[#6F7789]">No power-unit penalty decided this weekend.</p>;
  }
  return (
    <ul className="space-y-1.5 pt-3">
      {section.decisions.map((decision) => (
        <li key={`${decision.car_number}-${decision.url}`} className="flex items-start gap-2 text-xs text-[#B7BDCA]">
          <Link
            href={`/race-control/power-units/${decision.car_number}`}
            className="font-bold text-white hover:underline"
          >
            #{decision.car_number} {decision.driver.name}
          </Link>
          <span className="text-[#FF8A85]">{outcomeLabel(decision)}</span>
          <a href={decision.url} target="_blank" rel="noreferrer" className="ml-auto text-[#6F7789] hover:text-white">
            <ExternalLink className="h-3.5 w-3.5" aria-label={`FIA document: ${decision.title}`} />
          </a>
        </li>
      ))}
    </ul>
  );
}

/**
 * Two things worth knowing before the weekend starts: who won and took pole
 * the last time F1 raced here, and any power-unit penalty already decided —
 * each from its source of record, f1db and the FIA's documents.
 */
export function WeekendGlance({ year, round }: { year: number; round: number }) {
  const { data, error } = useSWR<RaceGlance, Error>(`${API_BASE}/api/race-control/glance/${year}/${round}`, fetcher, {
    revalidateOnFocus: false,
    dedupingInterval: 300000,
  });

  return (
    <ConsolePanel>
      <ConsoleHeader label="At a glance" />
      <div className="p-4 font-mono text-sm">
        {error && <p className="text-xs text-[#FFB4B1]">This round&apos;s history could not be loaded.</p>}
        {!data && !error && <p className="text-xs text-[#6F7789]">Reading this circuit&apos;s history…</p>}
        {data && (
          <>
            <dl className="divide-y divide-[#1E2633]">
              <InfoRow
                label={data.previous ? `${data.previous.year} winner` : "Last winner"}
                value={<HeadlinerValue person={data.previous?.winner ?? null} />}
              />
              <InfoRow
                label={data.previous ? `${data.previous.year} pole` : "Last pole"}
                value={<HeadlinerValue person={data.previous?.pole ?? null} />}
              />
            </dl>
            {!data.previous && <p className="pt-2 text-xs text-[#6F7789]">No earlier race at this circuit.</p>}
            <PenaltyList section={data.power_units} />
          </>
        )}
      </div>
    </ConsolePanel>
  );
}
