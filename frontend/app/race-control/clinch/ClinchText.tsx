"use client";

/**
 * The clinch calculator's lines, where the pages print them. Each renders only
 * what `app/lib/clinch` returns: no title arithmetic happens here. A failed
 * read, a season the calculator does not cover, or nothing to say all render
 * nothing (never "unavailable"): the lines add to a page, they don't hold it up.
 */

import { clinchAside, entrantClause, heroSentence, type ChampionshipTable, type ClinchEntrant } from "@/app/lib/clinch";
import { SectionSkeleton, StaleMark } from "@/app/ui/section/Section";
import { EYEBROW } from "@/app/ui/typography";

import { useClinch } from "./useClinch";

interface ClinchLineProps {
  year: number;
  table: ChampionshipTable;
}

interface ClinchHeroLineProps extends ClinchLineProps {
  /** The plain lead line, printed when the calculator has no sentence. */
  fallback: string;
}

/** The hero's sentence under a championship: where it was clinched, or what the leader must do next. */
export function ClinchHeroLine({ year, table, fallback }: ClinchHeroLineProps) {
  const state = useClinch(year);
  // Two lines of the 17px sentence, its usual length, so the hero holds still when it lands.
  if (state.status === "pending") return <SectionSkeleton className="h-[51px] max-w-[46ch]" />;
  const title = state.data?.[table];
  const parts = title ? heroSentence(table, title) : null;
  return (
    <div className="max-w-[46ch]">
      <p className="text-[17px] text-rc-ink-2 text-pretty motion-safe:animate-fade-up">
        {parts ? (
          <>
            {parts.strong && <b className="font-semibold text-rc-ink">{parts.strong}</b>}
            {parts.rest}
          </>
        ) : (
          fallback
        )}
      </p>
      {state.status === "stale" && <StaleMark state={state} className="mt-2" />}
    </div>
  );
}

/** The short caption beside a championship's heading: "Mercedes can clinch in São Paulo". */
export function ClinchAside({ year, table }: ClinchLineProps) {
  const state = useClinch(year);
  if (state.status === "pending") return <SectionSkeleton className="h-4 w-48" />;
  const title = state.data?.[table];
  const text = title ? clinchAside(table, title) : null;
  if (!text) return null;
  return (
    <div className="flex flex-wrap items-center justify-end gap-x-3 gap-y-1">
      <p className={EYEBROW}>{text}</p>
      {state.status === "stale" && <StaleMark state={state} />}
    </div>
  );
}

/** One team's or driver's own clause, after their standing sentence: inline, so it can sit in that sentence's `<p>`. */
export function EntrantClinch({ year, table, entrant }: ClinchLineProps & { entrant: ClinchEntrant }) {
  const state = useClinch(year);
  const title = state.data?.[table];
  const text = title ? entrantClause(table, title, entrant) : null;
  if (!text) return null;
  return (
    <>
      {" "}
      <span className="motion-safe:animate-fade-up">{text}</span>
      {state.status === "stale" && <StaleMark state={state} as="span" className="mt-1" />}
    </>
  );
}
