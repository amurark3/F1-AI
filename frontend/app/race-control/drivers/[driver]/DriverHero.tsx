import { DriverName } from "@/app/ui/names/DriverName";
import { TeamName } from "@/app/ui/names/TeamName";
import { PageHero } from "@/app/ui/PageHero";

import { EntrantClinch } from "../../clinch/ClinchText";

import { formGuide, standingLine } from "./driverModel";
import { FormGuide } from "./FormGuide";

import type { DriverProfile } from "../../profiles/profilesModel";

/** The car number, large, in the team's colour: decoration for sighted readers, "Car 44" for the rest. */
function CarNumber({ number, color }: { number: number; color: string }) {
  return (
    <>
      <b
        aria-hidden="true"
        className="block font-display text-[96px] font-extrabold leading-[0.8] sm:text-[200px]"
        style={{ color }}
      >
        {number}
      </b>
      <span className="sr-only">Car {number}</span>
    </>
  );
}

function OtherTeams({ profile }: { profile: DriverProfile }) {
  const others = profile.teams.filter((spell) => spell.id !== profile.driver.team_id);
  return (
    <>
      {others.map((spell) => (
        <p key={spell.id} className="font-mono text-[11px] font-medium leading-none text-rc-ink-3">
          Also drove for <TeamName name={spell.name} id={spell.id} year={profile.year} /> ({spell.rounds_label})
        </p>
      ))}
    </>
  );
}

/** The driver's band: car number, name, place and standing sentence, and the last five races on the right. */
export function DriverHero({ profile }: { profile: DriverProfile }) {
  const { driver, year } = profile;
  const chips = formGuide(profile);
  const eyebrow = (
    <>
      <TeamName name={driver.team_name} id={driver.team_id} year={year} />
      {driver.nationality ? ` · ${driver.nationality}` : ""} · {year}
    </>
  );
  return (
    <PageHero
      band
      accent={driver.color}
      lead={driver.number === null ? undefined : <CarNumber number={driver.number} color={driver.color} />}
      eyebrow={eyebrow}
      title={
        <DriverName name={driver.name} lastName={driver.last_name} code={driver.code} id={driver.id} year={year} />
      }
      meta={
        <>
          {standingLine(profile)}
          <EntrantClinch year={year} table="drivers" entrant={{ name: driver.name, code: driver.code }} />
        </>
      }
      aside={chips.length === 0 ? undefined : <FormGuide chips={chips} />}
    >
      {profile.teams.length > 1 ? (
        <div className="flex flex-col gap-1.5">
          <OtherTeams profile={profile} />
        </div>
      ) : undefined}
    </PageHero>
  );
}
