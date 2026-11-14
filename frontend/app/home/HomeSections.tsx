import { ArrowRight } from "lucide-react";
import Link from "next/link";

import { SectionHead } from "@/app/ui/SectionHead";
import { WRAP } from "@/app/ui/shell/wrap";
import { EYEBROW } from "@/app/ui/typography";

import { AI_ENGINEER, COMMAND_CENTER, REFERENCE, TOOLS, type HomeLink } from "./content";
import { RacingLine, ToolMotifStrip } from "./motifs";

/** The mockups' `.panel.card`: a whole-card link that warms to red on hover. */
const CARD =
  "group relative flex min-w-0 flex-col rounded-md border border-rc-line bg-(--surface) p-7 transition-colors hover:border-f1-red/75";
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

function RaceWeekend() {
  return (
    <HomeSection index={1} id="home-weekend" title="Race weekend">
      <div className="grid gap-5 lg:grid-cols-[7fr_5fr]">
        <Link href={COMMAND_CENTER.href} className={CARD}>
          <CardArrow />
          <div className="grid items-center gap-6 lg:grid-cols-[1fr_1.1fr]">
            <div>
              <p className={EYEBROW}>{COMMAND_CENTER.eyebrow}</p>
              <h3 className={CARD_TITLE}>{COMMAND_CENTER.title}</h3>
              <p className={CARD_TEXT}>{COMMAND_CENTER.description}</p>
            </div>
            <RacingLine />
          </div>
        </Link>
        <Link href={AI_ENGINEER.href} className={CARD}>
          <CardArrow />
          <p className={EYEBROW}>{AI_ENGINEER.eyebrow}</p>
          <h3 className={CARD_TITLE}>{AI_ENGINEER.title}</h3>
          <p className={CARD_TEXT}>{AI_ENGINEER.description}</p>
          <ul aria-label="Questions to try" className="mt-auto grid gap-2 pt-[22px]">
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
      </div>
    </HomeSection>
  );
}

function DecisionTools() {
  return (
    <HomeSection index={2} id="home-tools" title="Decision tools">
      <div className="grid gap-5 lg:grid-cols-6">
        {TOOLS.map((tool) => (
          <Link key={tool.href} href={tool.href} className={`${CARD} ${tool.wide ? "lg:col-span-3" : "lg:col-span-2"}`}>
            <CardArrow />
            <ToolMotifStrip motif={tool.motif} />
            <h3 className={CARD_TITLE}>{tool.title}</h3>
            <p className={CARD_TEXT}>{tool.description}</p>
          </Link>
        ))}
      </div>
    </HomeSection>
  );
}

function ReferenceRow({ link, number }: { link: HomeLink; number: string }) {
  return (
    <Link
      href={link.href}
      className="group grid grid-cols-[36px_1fr_auto] items-baseline gap-x-6 gap-y-2 border-b border-rc-line px-1 py-[22px] transition-colors hover:bg-rc-hero lg:grid-cols-[56px_300px_1fr_auto]"
    >
      <span aria-hidden="true" className="font-mono text-xs font-semibold leading-none text-rc-ink-3">
        {number}
      </span>
      <h3 className="font-display text-[28px] font-extrabold uppercase leading-none text-rc-ink">{link.title}</h3>
      <p className="col-start-2 text-sm text-rc-ink-2 lg:col-start-auto">{link.description}</p>
      <ArrowRight
        aria-hidden="true"
        className="size-4 self-center text-rc-ink-3 transition-transform group-hover:translate-x-1 group-hover:text-rc-red-text"
      />
    </Link>
  );
}

function Reference() {
  return (
    <HomeSection index={3} id="home-reference" title="Reference">
      <div>
        {REFERENCE.map((link, index) => (
          <ReferenceRow key={link.href} link={link} number={`03.${index + 1}`} />
        ))}
      </div>
    </HomeSection>
  );
}

/** Sections 01–03 of home.html: every screen, grouped by when you reach for it. */
export function HomeSections() {
  return (
    <div className={GRID_TEXTURE}>
      <div className={`${WRAP} pb-[120px]`}>
        <RaceWeekend />
        <DecisionTools />
        <Reference />
      </div>
    </div>
  );
}
