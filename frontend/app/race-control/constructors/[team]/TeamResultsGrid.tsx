/**
 * Every round of the team's season: each driver's finish, and the points the
 * team scored that weekend.
 *
 * One column per driver who raced for the team, so a stand-in's rounds sit in
 * their own column rather than being credited to the driver they replaced.
 * Sprint results sit under the grand prix finish, marked "S".
 *
 * Server-safe: no state, no effects.
 */
import Link from "next/link";

import { driverHref, grandPrixHref } from "@/app/lib/entityLinks";
import { PanelHeading } from "@/app/ui/PanelHeading";

import { Panel } from "../../components/RaceControlPrimitives";
import { FinishChip } from "../../profiles/FinishChip";
import { formatPoints, type TeamDriver, type TeamProfile, type TeamRound } from "../../profiles/profilesModel";

function DriverCell({ round, driverId }: { round: TeamRound; driverId: string }) {
  if (round.status === "pending") {
    return <td className="px-2 py-2 text-center text-xs text-[#3A4352]">·</td>;
  }
  const result = round.results.find((item) => item.driver_id === driverId);
  return (
    <td className="px-2 py-2 text-center">
      <div className="flex flex-col items-center gap-1">
        <FinishChip finish={result?.race ?? null} />
        {result?.sprint && (
          <span className="flex items-center gap-1 text-[10px] text-[#6F7789]">
            S <FinishChip finish={result.sprint} size="sm" />
          </span>
        )}
      </div>
    </td>
  );
}

function RoundRow({ round, drivers }: { round: TeamRound; drivers: TeamDriver[] }) {
  const pending = round.status === "pending";
  return (
    <tr className={pending ? "text-[#5A6273]" : "text-[#D4D8E0]"}>
      <td className="px-3 py-2 font-mono text-xs font-bold text-[#6F7789]">R{round.round}</td>
      <td className="max-w-[16rem] truncate px-3 py-2 text-sm">
        {pending ? (
          <span>{round.short_name}</span>
        ) : (
          <Link href={grandPrixHref(round.round, "sessions")} className="font-bold text-white hover:underline">
            {round.short_name}
          </Link>
        )}
      </td>
      {drivers.map((driver) => (
        <DriverCell key={driver.id} round={round} driverId={driver.id} />
      ))}
      <td className="px-3 py-2 text-right font-mono text-sm font-bold tabular-nums">
        {pending ? "—" : formatPoints(round.points)}
      </td>
    </tr>
  );
}

export function TeamResultsGrid({ profile }: { profile: TeamProfile }) {
  const { drivers, rounds } = profile;
  return (
    <Panel as="section" className="mb-5">
      <PanelHeading
        eyebrow="Every round"
        aside={<span className="text-xs text-[#6F7789]">Hover a result for grid, places gained and reason</span>}
        inset
      />
      <div className="overflow-x-auto">
        <table className="w-full min-w-[560px] border-collapse">
          <caption className="sr-only">
            {profile.team.name} results by round, one column per driver, with the team&apos;s points
          </caption>
          <thead>
            <tr className="border-b border-[#1E2633] text-left font-mono text-[10px] uppercase tracking-[0.18em] text-[#6F7789]">
              <th scope="col" className="px-3 py-2">
                Rd
              </th>
              <th scope="col" className="px-3 py-2">
                Grand prix
              </th>
              {drivers.map((driver) => (
                <th key={driver.id} scope="col" className="px-2 py-2 text-center">
                  <Link href={driverHref(driver.id)} className="hover:text-white" title={driver.name}>
                    {driver.code ?? driver.name}
                  </Link>
                </th>
              ))}
              <th scope="col" className="px-3 py-2 text-right">
                Pts
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[#1E2633]">
            {rounds.map((round) => (
              <RoundRow key={round.round} round={round} drivers={drivers} />
            ))}
          </tbody>
        </table>
      </div>
    </Panel>
  );
}
