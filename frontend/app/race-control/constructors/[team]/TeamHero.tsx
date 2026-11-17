import { TeamName } from "@/app/ui/names/TeamName";
import { PageHero } from "@/app/ui/PageHero";

import { TeamLineUp } from "./TeamLineUp";
import { standingLine } from "./teamModel";

import type { TeamProfile } from "../../profiles/profilesModel";
import type { ReactNode } from "react";

interface TeamHeroProps {
  profile: TeamProfile;
  /** Sits right after the standing sentence, e.g. "Can clinch in São Paulo." */
  clinch?: ReactNode;
}

/** The team's band: name, place and standing sentence on the left, its cars on the right. */
export function TeamHero({ profile, clinch }: TeamHeroProps) {
  const { team, year } = profile;
  const meta = team.power_unit ? `${team.full_name} · ${team.power_unit} power unit` : team.full_name;
  return (
    <PageHero
      band
      accent={team.color}
      eyebrow={`Constructors' championship · ${year}`}
      title={<TeamName name={team.name} fullName={team.full_name} id={team.id} year={year} variant="name" />}
      meta={meta}
      aside={<TeamLineUp profile={profile} />}
    >
      <div className="flex items-baseline gap-4">
        <b className="font-display text-[76px] font-extrabold leading-[0.9] text-rc-ink">
          {team.position === null ? "—" : `P${team.position}`}
        </b>
        <span className="max-w-[26ch] text-[15px] text-rc-ink-2">
          {standingLine(profile)}
          {clinch}
        </span>
      </div>
    </PageHero>
  );
}
