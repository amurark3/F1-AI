"use client";

import { ArrowRight } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import SiteFooter from "./SiteFooter";

/**
 * Chrome for everything outside the Race Control workspace — in practice just the
 * landing page, since every other top-level route redirects into /race-control.
 *
 * There is deliberately no tab bar here. The app's real navigation is the Race
 * Control sidebar; the old top tabs duplicated it through redirect stubs that had
 * drifted out of date (Calendar pointed at the command center, not a calendar).
 * The logo returns home and the CTA enters the app — that is the whole surface.
 */
export default function NavShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();

  // Race Control ships its own full-height shell with a sidebar.
  if (pathname?.startsWith("/race-control")) {
    return <>{children}</>;
  }

  return (
    <main className="flex min-h-screen flex-col" style={{ background: "#07090D" }}>
      {/* Top speed stripe */}
      <div
        className="relative h-[3px] overflow-hidden"
        style={{ background: "linear-gradient(90deg, #E10600 0%, #FF4422 50%, #E10600 100%)" }}
      >
        <div
          className="absolute inset-y-0 w-1/3 animate-streak motion-reduce:hidden"
          style={{ background: "linear-gradient(90deg, transparent, rgba(255,255,255,0.45), transparent)" }}
        />
      </div>

      <header className="glass-strong sticky top-0 z-50 border-b border-white/5">
        <div className="mx-auto flex h-14 max-w-7xl items-center justify-between gap-4 px-4 sm:px-6">
          <Link href="/" className="flex shrink-0 items-center" aria-label="F1 AI home">
            <span
              className="select-none text-[22px] font-black italic uppercase leading-none tracking-tighter"
              style={{ fontFamily: "var(--font-barlow, var(--font-geist-sans))" }}
            >
              <span className="text-white">F1</span>
              <span className="ml-1" style={{ color: "#E10600" }}>
                AI
              </span>
            </span>
          </Link>

          <Link
            href="/race-control"
            className="inline-flex items-center gap-2 rounded-md border border-[#1E2633] px-3 py-1.5 text-[11px] font-black uppercase tracking-widest text-neutral-400 transition-colors hover:border-white/20 hover:bg-white/[0.04] hover:text-white focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-[#E10600]/40"
            style={{ fontFamily: "var(--font-barlow, var(--font-geist-sans))" }}
          >
            Race Control
            <ArrowRight className="h-3.5 w-3.5" />
          </Link>
        </div>
      </header>

      <div className="flex-1">{children}</div>

      <SiteFooter />
    </main>
  );
}
