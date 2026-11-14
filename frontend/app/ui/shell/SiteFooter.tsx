import Link from "next/link";

import { MORE_NAV, PRIMARY_NAV } from "./navConfig";
import { WRAP } from "./wrap";

/**
 * Trade-mark disclaimer required of any unofficial Formula 1 site. The wording is
 * the standard form used across fan sites — it must stay verbatim, so it lives in
 * one constant rather than being reworded per surface.
 */
const F1_DISCLAIMER =
  "This site is unofficial and is not associated in any way with the Formula 1 companies. " +
  "F1, FORMULA ONE, FORMULA 1, FIA FORMULA ONE WORLD CHAMPIONSHIP, GRAND PRIX and related " +
  "marks are trade marks of Formula One Licensing B.V.";

/** Every source the site reads, credited by name (Open-Meteo's licence asks for attribution). */
const DATA_SOURCES = [
  { label: "f1db", href: "https://github.com/f1db/f1db" },
  { label: "OpenF1", href: "https://openf1.org" },
  { label: "FastF1", href: "https://github.com/theOehrly/Fast-F1" },
  { label: "Open-Meteo", href: "https://open-meteo.com" },
  { label: "OpenWeatherMap", href: "https://openweathermap.org" },
];

/** The footer lists the top bar's sections, then the screens under More. */
const FOOTER_NAV = [...PRIMARY_NAV, ...MORE_NAV];

const QUIET_LINK = "transition-colors hover:text-rc-ink";

/** Fine-print disclaimer for full-bleed workspaces that have no room for a footer. */
export function F1DisclaimerLine({ className = "" }: { className?: string }) {
  return <p className={`text-[10px] leading-snug text-rc-ink-3 ${className}`}>{F1_DISCLAIMER}</p>;
}

/**
 * The foot of every page but the workspaces (the mockups' `footer`): the
 * screens from `navConfig`, the one source of the header's links too, then
 * the disclaimer beside the data credits.
 */
export function SiteFooter() {
  return (
    <footer className="border-t border-rc-line text-xs text-rc-ink-3">
      <div className={`${WRAP} pb-12 pt-9`}>
        <nav aria-label="Footer">
          <ul className="flex flex-wrap gap-x-6 gap-y-3 font-mono text-[11px] font-medium uppercase leading-none tracking-[0.18em]">
            {FOOTER_NAV.map(({ href, label }) => (
              <li key={href}>
                <Link href={href} className={QUIET_LINK}>
                  {label}
                </Link>
              </li>
            ))}
          </ul>
        </nav>
        <div className="mt-8 flex flex-wrap justify-between gap-x-12 gap-y-4 border-t border-rc-line-soft pt-6">
          <p className="max-w-2xl leading-relaxed">{F1_DISCLAIMER}</p>
          <p className="font-mono">
            Data:{" "}
            {DATA_SOURCES.map(({ label, href }, i) => (
              <span key={label}>
                {i > 0 && " · "}
                <a href={href} target="_blank" rel="noopener noreferrer" className={QUIET_LINK}>
                  {label}
                </a>
              </span>
            ))}
          </p>
        </div>
      </div>
    </footer>
  );
}
