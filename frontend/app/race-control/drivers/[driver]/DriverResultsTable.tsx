/**
 * Every round of the driver's season, including the ones they sat out — a seat
 * swap reads as a gap ("—"), not as a renumbered season.
 *
 * Server-safe: no state, no effects.
 */
import Link from "next/link";

import { grandPrixHref, teamHref } from "@/app/lib/entityLinks";
import { DriverName } from "@/app/ui/names/DriverName";
import { TeamName } from "@/app/ui/names/TeamName";
import { PanelHeading } from "@/app/ui/PanelHeading";

import { Panel } from "../../components/RaceControlPrimitives";
import { FinishChip } from "../../profiles/FinishChip";
import { formatPoints, type DriverProfile, type DriverRound } from "../../profiles/profilesModel";

function gained(round: DriverRound): string {
  const value = round.race?.positions_gained;
  if (value === null || value === undefined) return "—";
  return value > 0 ? `+${value}` : String(value);
}

function RoundCells({ round, teamNames }: { round: DriverRound; teamNames: Map<string, string> }) {
  const { race, sprint } = round;
  const raced = race !== null || sprint !== null;
  return (
    <>
      <td className="px-3 py-2 text-xs">
        {round.team_id ? (
          <Link href={teamHref(round.team_id)} className="text-[#B7BDCA] hover:text-white hover:underline">
            <TeamName name={teamNames.get(round.team_id) ?? round.team_id} id={round.team_id} />
          </Link>
        ) : (
          <span className="text-[#5A6273]">{round.status === "complete" ? "Did not race" : ""}</span>
        )}
      </td>
      <td className="px-3 py-2 text-center font-mono text-xs tabular-nums">{race?.grid ? `P${race.grid}` : "—"}</td>
      <td className="px-3 py-2 text-center">
        {raced || round.status === "complete" ? <FinishChip finish={race} /> : "·"}
      </td>
      <td className="px-3 py-2 text-center font-mono text-xs tabular-nums">{gained(round)}</td>
      <td className="px-3 py-2 text-center">
        {sprint ? <FinishChip finish={sprint} size="sm" /> : <span className="text-[#3A4352]">—</span>}
      </td>
      <td className="px-3 py-2 text-right font-mono text-sm font-bold tabular-nums">
        {raced ? formatPoints((race?.points ?? 0) + (sprint?.points ?? 0)) : "—"}
      </td>
    </>
  );
}

export function DriverResultsTable({ profile }: { profile: DriverProfile }) {
  const teamNames = new Map(profile.teams.map((spell) => [spell.id, spell.name]));
  return (
    <Panel as="section" className="mb-5">
      <PanelHeading
        eyebrow="Every round"
        aside={<span className="text-xs text-[#6F7789]">Hover a result for its grid slot and reason</span>}
        inset
      />
      <div className="overflow-x-auto">
        <table className="w-full min-w-[640px] border-collapse">
          <caption className="sr-only">
            <DriverName
              name={profile.driver.name}
              code={profile.driver.code}
              id={profile.driver.id}
              year={profile.year}
            />
            &apos;s result in every round of {profile.year}
          </caption>
          <thead>
            <tr className="border-b border-[#1E2633] text-left font-mono text-[10px] uppercase tracking-[0.18em] text-[#6F7789]">
              <th scope="col" className="px-3 py-2">
                Rd
              </th>
              <th scope="col" className="px-3 py-2">
                Grand prix
              </th>
              <th scope="col" className="px-3 py-2">
                Team
              </th>
              <th scope="col" className="px-3 py-2 text-center">
                Grid
              </th>
              <th scope="col" className="px-3 py-2 text-center">
                Finish
              </th>
              <th scope="col" className="px-3 py-2 text-center">
                +/−
              </th>
              <th scope="col" className="px-3 py-2 text-center">
                Sprint
              </th>
              <th scope="col" className="px-3 py-2 text-right">
                Pts
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[#1E2633]">
            {profile.rounds.map((round) => (
              <tr key={round.round} className={round.status === "pending" ? "text-[#5A6273]" : "text-[#D4D8E0]"}>
                <td className="px-3 py-2 font-mono text-xs font-bold text-[#6F7789]">R{round.round}</td>
                <td className="max-w-[14rem] truncate px-3 py-2 text-sm">
                  {round.status === "complete" ? (
                    <Link
                      href={grandPrixHref(round.round, "sessions")}
                      className="font-bold text-white hover:underline"
                    >
                      {round.short_name}
                    </Link>
                  ) : (
                    round.short_name
                  )}
                </td>
                <RoundCells round={round} teamNames={teamNames} />
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Panel>
  );
}
