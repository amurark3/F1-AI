import { ArrowRight } from "lucide-react";
import Image from "next/image";
import Link from "next/link";

import { WRAP } from "@/app/ui/shell/wrap";
import { DISPLAY, EYEBROW } from "@/app/ui/typography";

import { HERO_CTAS } from "./content";

const RISE = "motion-safe:animate-fade-up";

/** The mockups' `.btn`: condensed caps on a 48 px bar. */
const BUTTON =
  "inline-flex h-12 items-center gap-2.5 border px-6 font-display text-[19px] font-extrabold uppercase leading-none tracking-[0.02em] transition-colors";

/**
 * The photo hero (home.html `.hero`): the car carries the mood, the type the
 * message. Two scrims keep the headline legible: one from the left, where the
 * words sit, one up from the bottom into the page.
 */
export function HomeHero() {
  return (
    <section
      aria-labelledby="home-title"
      className="relative isolate flex min-h-[min(86vh,780px)] items-center overflow-hidden"
    >
      <Image
        src="/hero-car.jpg"
        alt=""
        fill
        preload
        sizes="100vw"
        className="-z-20 object-cover object-[62%_50%] lg:object-[70%_55%]"
      />
      <div
        aria-hidden="true"
        className="absolute inset-0 -z-10 bg-linear-to-r from-background/90 to-background/55 lg:from-background lg:via-background/90 lg:via-30% lg:to-background/10"
      />
      <div aria-hidden="true" className="absolute inset-0 -z-10 bg-linear-to-t from-background to-transparent to-30%" />

      <div className={`${WRAP} pb-[88px] pt-[72px] lg:pb-[112px]`}>
        <p className={`${EYEBROW} ${RISE}`}>Formula 1 race intelligence</p>
        <h1
          id="home-title"
          className={`${DISPLAY} mt-[22px] text-[clamp(54px,11vw,176px)] text-rc-ink ${RISE} [animation-delay:80ms]`}
        >
          <span className="block">Your AI</span>
          <span className="block text-rc-red-text">Race Engineer</span>
        </h1>
        <div
          aria-hidden="true"
          className="mb-6 mt-7 h-[3px] w-24 origin-left bg-f1-red motion-safe:animate-fill-x [animation-delay:300ms]"
        />
        <p className={`max-w-[46ch] text-lg leading-[1.6] text-rc-ink-2 text-pretty ${RISE} [animation-delay:200ms]`}>
          Live timing, championship stakes and a prediction model trained on seven decades of results — with an engineer
          that explains any of it on request.
        </p>
        <div className={`mt-9 flex flex-wrap gap-3.5 ${RISE} [animation-delay:300ms]`}>
          <Link
            href={HERO_CTAS.primary.href}
            className={`${BUTTON} border-transparent bg-f1-red text-rc-ink hover:brightness-110`}
          >
            {HERO_CTAS.primary.label}
            <ArrowRight aria-hidden="true" className="size-5" />
          </Link>
          <Link
            href={HERO_CTAS.secondary.href}
            className={`${BUTTON} border-rc-ink/35 text-rc-ink hover:border-rc-ink`}
          >
            {HERO_CTAS.secondary.label}
          </Link>
        </div>
      </div>
    </section>
  );
}
