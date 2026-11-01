"use client";

import useSWR from "swr";

import { API_BASE } from "@/app/constants/api";
import { awaitingFirstData, seededWith } from "@/app/lib/swrFallback";
import { fetcher } from "@/app/utils/fetcher";

import { ConsoleHeader, ConsolePanel } from "../../grand-prix/predictionConsole";
import { PowerUnitsSection, type DriverFocus } from "../../profiles/PowerUnitCards";
import { FinishPositionChart } from "../../profiles/ProfileCharts";
import {
  isDriverProfile,
  profilesUrl,
  type DriverCar,
  type DriverProfile,
  type DriverProfileResponse,
} from "../../profiles/profilesModel";
import { ProfileLoading, ProfileNotFound, ProfileUnavailable } from "../../profiles/ProfileStates";

import { DriverHeader, DriverWins } from "./DriverHeader";
import { DriverResultsTable } from "./DriverResultsTable";

/** A full 2026 grid; the axis grows if a result ever sits lower. */
const FIELD_SIZE = 22;

function PositionPanel({ profile }: { profile: DriverProfile }) {
  const data = profile.rounds
    .filter((round) => round.status === "complete")
    .map((round) => ({ label: `R${round.round}`, name: round.short_name, position: round.race?.position ?? null }));
  const raced = data.filter((entry) => entry.position !== null);
  if (raced.length < 2) return null;
  const lowest = Math.max(...raced.map((entry) => entry.position ?? 0));
  return (
    <ConsolePanel className="mb-5">
      <ConsoleHeader
        label="Finishing position by round"
        right={<span className="text-xs text-[#6F7789]">Gaps are retirements or rounds not raced</span>}
      />
      <div className="p-3">
        <FinishPositionChart data={data} color={profile.driver.color} fieldSize={Math.max(FIELD_SIZE, lowest)} />
      </div>
    </ConsolePanel>
  );
}

function focusFor(profile: DriverProfile): (car: DriverCar) => DriverFocus {
  return (car) => ({ driverName: profile.driver.name, rounds: car.driver_rounds, sharedWith: car.shared_with });
}

function DriverPage({ profile }: { profile: DriverProfile }) {
  return (
    <div>
      <DriverHeader profile={profile} />
      <div className="grid gap-x-5 xl:grid-cols-[minmax(0,1fr)_minmax(0,2fr)]">
        <DriverWins profile={profile} />
        <PositionPanel profile={profile} />
      </div>
      <DriverResultsTable profile={profile} />
      <PowerUnitsSection section={profile.power_units} color={profile.driver.color} renderFocus={focusFor(profile)} />
    </div>
  );
}

export function DriverView({
  driverId,
  year,
  initial,
}: {
  driverId: string;
  year: number;
  initial: DriverProfileResponse | null;
}) {
  const { data, error, isLoading, mutate } = useSWR<DriverProfileResponse, Error>(
    profilesUrl(API_BASE, year, `drivers/${encodeURIComponent(driverId)}`),
    fetcher,
    { revalidateOnFocus: false, dedupingInterval: 180000, ...seededWith(initial) },
  );

  if (awaitingFirstData(isLoading, data !== undefined)) {
    return <ProfileLoading what="driver" />;
  }
  if (isDriverProfile(data)) {
    return <DriverPage profile={data} />;
  }
  if (data?.status === "not_found") {
    return <ProfileNotFound what="driver" backHref="/race-control/constructors" backLabel="All teams" />;
  }
  return <ProfileUnavailable onRetry={() => void mutate()} errorId={error ? undefined : data?.error_id} />;
}
