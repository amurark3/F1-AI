import { DriverName } from "@/app/ui/names/DriverName";
import { TeamName } from "@/app/ui/names/TeamName";
import { EYEBROW } from "@/app/ui/typography";

import { StateTag } from "../grand-prix/StateTag";
import { formatPoints } from "../standings/teamsModel";

import type { DebriefTitle } from "./debriefTypes";

/** "with 4 races to spare", "with 1 race to spare", or "at the final round"; empty when the data does not say. */
export function sparePhrase(racesLeft: number | null): string {
  if (racesLeft === null) return "";
  if (racesLeft === 0) return " at the final round";
  return ` with ${racesLeft} ${racesLeft === 1 ? "race" : "races"} to spare`;
}

function Champion({ title }: { title: DebriefTitle }) {
  return title.table === "drivers" ? (
    <DriverName name={title.name} className="font-semibold text-rc-ink" />
  ) : (
    <TeamName name={title.name} className="font-semibold text-rc-ink" />
  );
}

function Banner({ title, year }: { title: DebriefTitle; year: number }) {
  const drivers = title.table === "drivers";
  const margin =
    title.lead !== null && title.runner_up !== null ? `, ${formatPoints(title.lead)} clear of ${title.runner_up}` : "";
  return (
    <div
      data-title={title.table}
      className="flex flex-wrap items-center gap-x-4 gap-y-1 rounded-md border border-rc-gold/35 bg-rc-gold/[0.06] px-[18px] py-3.5"
    >
      <p className={`${EYEBROW} text-rc-gold`}>{drivers ? "Champion" : "Constructors' champion"}</p>
      <p className="min-w-0 text-sm text-rc-ink-2">
        <Champion title={title} />
        {` · ${year} World Champion${drivers ? "" : "s"}${sparePhrase(title.races_left)} · ${formatPoints(title.points)} points${margin}`}
      </p>
      {title.provisional && <StateTag tone="blue">Provisional</StateTag>}
    </div>
  );
}

/** One banner per championship clinched at this race. */
export function TitleBanners({ titles, year }: { titles: readonly DebriefTitle[]; year: number }) {
  if (titles.length === 0) return null;
  return (
    <div className="space-y-3">
      {titles.map((title) => (
        <Banner key={title.table} title={title} year={year} />
      ))}
    </div>
  );
}
