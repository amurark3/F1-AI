import { ArrowRight } from "lucide-react";
import Link from "next/link";

import { SectionHead } from "@/app/ui/SectionHead";
import { COMMAND_CENTER_LINK, ENGINEER_LINK, RACES, REFERENCE, SEASON } from "@/app/ui/shell/navConfig";
import { WRAP } from "@/app/ui/shell/wrap";
import { EYEBROW } from "@/app/ui/typography";

import {
  AI_ENGINEER,
  COMMAND_CENTER,
  RACE_CARDS,
  REFERENCE_CARDS,
  SEASON_CARDS,
  type HomeLink,
  type ToolMotif,
} from "./content";
import { RacingLine, ToolMotifStrip } from "./motifs";

/** The mockups' `.panel.card`: a whole-card link that warms to red on hover. */
const CARD =
  "group relative min-w-0 rounded-md border border-rc-line bg-(--surface) p-7 transition-colors hover:border-f1-red/75";
const FEATURE_CARD = `${CARD} grid items-center gap-6 sm:grid-cols-[minmax(0,7fr)_minmax(0,5fr)] sm:gap-10`;
const CARD_TITLE = "my-2.5 font-display text-[30px] font-extrabold uppercase leading-none text-rc-ink text-balance";
const CARD_TEXT = "max-w-[44ch] text-sm text-rc-ink-2 text-pretty";

/** A faint 80 px grid behind the sections (home.html `main`): the row-divider hairline at half strength. */
const GRID_TEXTURE =
  "bg-[linear-gradient(color-mix(in_srgb,var(--rc-line-soft)_50%,transparent)_1px,transparent_1px),linear-gradient(90deg,color-mix(in_srgb,var(--rc-line-soft)_50%,transparent)_1px,transparent_1px)] bg-size-[80px_80px]";

function CardArrow() {
  return (
    <ArrowRight
      aria-hidden="true"
      className="absolute right-7 top-7 size-4 text-rc-ink-3 transition-transform group-hover:translate-x-1 group-hover:text-rc-red-text"
    />
  );
}

/** A numbered section with its condensed head; the region takes the head's name. */
function HomeSection({
  index,
  id,
  title,
  children,
}: {
  index: number;
  id: string;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section aria-labelledby={id} className="pt-[72px] lg:pt-[104px]">
      <SectionHead index={index} id={id} title={title} />
      {children}
    </section>
  );
}

function RaceControl() {
  return (
    <HomeSection index={1} id="home-race-control" title={COMMAND_CENTER_LINK.label}>
      <Link href={COMMAND_CENTER.href} className={FEATURE_CARD}>
        <CardArrow />
        <div>
          <p className={EYEBROW}>{COMMAND_CENTER.eyebrow}</p>
          <h3 className={CARD_TITLE}>{COMMAND_CENTER.title}</h3>
          <p className={CARD_TEXT}>{COMMAND_CENTER.description}</p>
        </div>
        <div className="w-full max-w-[280px] justify-self-center">
          <RacingLine />
        </div>
      </Link>
    </HomeSection>
  );
}

function Engineer() {
  return (
    <HomeSection index={5} id="home-engineer" title={ENGINEER_LINK.label}>
      <Link href={AI_ENGINEER.href} className={FEATURE_CARD}>
        <CardArrow />
        <div>
          <h3 className={CARD_TITLE}>{AI_ENGINEER.title}</h3>
          <p className={CARD_TEXT}>{AI_ENGINEER.description}</p>
        </div>
        <ul aria-label="Questions to try" className="grid gap-2 sm:pr-8">
          {AI_ENGINEER.questions.map((question) => (
            <li
              key={question}
              className="max-w-[85%] justify-self-end rounded-md bg-rc-raised px-3.5 py-2.5 text-[13px] leading-normal text-rc-ink"
            >
              {question}
            </li>
          ))}
        </ul>
      </Link>
    </HomeSection>
  );
}

function ToolCards({ cards, className }: { cards: ReadonlyArray<HomeLink & { motif: ToolMotif }>; className: string }) {
  return (
    <div className={`grid gap-5 ${className}`}>
      {cards.map((tool) => (
        <Link key={tool.href} href={tool.href} className={`${CARD} flex flex-col`}>
          <CardArrow />
          <ToolMotifStrip motif={tool.motif} />
          <h3 className={CARD_TITLE}>{tool.title}</h3>
          <p className={CARD_TEXT}>{tool.description}</p>
        </Link>
      ))}
    </div>
  );
}

export function HomeSections() {
  return (
    <div className={GRID_TEXTURE}>
      <div className={`${WRAP} pb-[120px]`}>
        <RaceControl />
        <HomeSection index={2} id="home-races" title={RACES.label}>
          <p className="-mt-3 mb-6 text-sm text-rc-ink-2">
            One race, four ways in. Pick a round once and move between them.
          </p>
          <ToolCards cards={RACE_CARDS} className="sm:grid-cols-2 lg:grid-cols-4" />
        </HomeSection>
        <HomeSection index={3} id="home-season" title={SEASON.label}>
          <ToolCards cards={SEASON_CARDS} className="sm:grid-cols-2 lg:grid-cols-3" />
        </HomeSection>
        <HomeSection index={4} id="home-reference" title={REFERENCE.label}>
          <ToolCards cards={REFERENCE_CARDS} className="sm:grid-cols-2" />
        </HomeSection>
        <Engineer />
      </div>
    </div>
  );
}
