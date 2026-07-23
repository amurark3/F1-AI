import Link from "next/link";

const rcMono = { fontFamily: "var(--font-geist-mono, var(--font-geist-sans, monospace))" };

/**
 * Trade-mark disclaimer required of any unofficial Formula 1 site. The wording is
 * the standard form used across fan sites — it must stay verbatim, so it lives in
 * one constant rather than being reworded per surface.
 */
const F1_DISCLAIMER =
  "This site is unofficial and is not associated in any way with the Formula 1 companies. " +
  "F1, FORMULA ONE, FORMULA 1, FIA FORMULA ONE WORLD CHAMPIONSHIP, GRAND PRIX and related " +
  "marks are trade marks of Formula One Licensing B.V.";

const DATA_SOURCES = [
  { label: "f1db", href: "https://github.com/f1db/f1db" },
  { label: "FastF1", href: "https://github.com/theOehrly/Fast-F1" },
  { label: "OpenWeatherMap", href: "https://openweathermap.org" },
];

interface SiteFooterProps {
  /** Single-line variant for the Race Control workspace, which is dense already. */
  compact?: boolean;
}

export default function SiteFooter({ compact = false }: SiteFooterProps) {
  const year = new Date().getFullYear();

  if (compact) {
    return (
      <footer className="border-t border-[#1E2633] px-4 py-4 sm:px-6">
        <p className="text-[11px] leading-relaxed text-[#5C6473]">
          {F1_DISCLAIMER}
        </p>
        <p className="mt-1.5 text-[11px] text-[#5C6473]">
          © {year} F1 AI — an independent project for research and education.
        </p>
      </footer>
    );
  }

  return (
    <footer className="mt-auto border-t border-[#1E2633] bg-[#080B11]">
      <div className="mx-auto w-full max-w-7xl px-4 py-8 sm:px-6">
        <div className="flex flex-col gap-6 sm:flex-row sm:justify-between">
          <div className="max-w-2xl">
            <p
              className="mb-2 text-[10px] font-black uppercase tracking-[0.22em] text-[#7F8797]"
              style={rcMono}
            >
              Disclaimer
            </p>
            <p className="text-xs leading-relaxed text-[#6F7789]">{F1_DISCLAIMER}</p>
          </div>

          <div className="shrink-0">
            <p
              className="mb-2 text-[10px] font-black uppercase tracking-[0.22em] text-[#7F8797]"
              style={rcMono}
            >
              Data Sources
            </p>
            <ul className="space-y-1">
              {DATA_SOURCES.map(({ label, href }) => (
                <li key={label}>
                  <a
                    href={href}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-xs text-[#6F7789] transition-colors hover:text-neutral-300"
                  >
                    {label}
                  </a>
                </li>
              ))}
            </ul>
          </div>
        </div>

        <div className="mt-7 flex flex-col gap-2 border-t border-[#141A24] pt-5 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-xs text-[#5C6473]">
            © {year} F1 AI — an independent project built for research and education.
          </p>
          <Link
            href="/race-control"
            className="text-xs font-semibold text-[#6F7789] transition-colors hover:text-neutral-200"
          >
            Enter Race Control →
          </Link>
        </div>
      </div>
    </footer>
  );
}
