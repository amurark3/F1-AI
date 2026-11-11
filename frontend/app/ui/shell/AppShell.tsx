"use client";

import { usePathname } from "next/navigation";

import SiteFooter from "@/app/components/SiteFooter";

import { layoutFor, type ShellLayout } from "./navConfig";
import { SiteHeader } from "./SiteHeader";
import { WRAP } from "./wrap";

/**
 * How each layout frames the page:
 * - `bare`: the homepage draws its own full-bleed sections.
 * - `workspace`: the AI Engineer fills the viewport under the bar and scrolls inside itself.
 * - `page`: every other screen sits in the page wrap (the mockups' `main.wrap.page`).
 */
const FRAME: Record<ShellLayout, { root: string; main: string }> = {
  bare: { root: "min-h-dvh", main: "flex-1" },
  workspace: { root: "h-dvh", main: "flex min-h-0 flex-1" },
  page: { root: "min-h-dvh", main: `${WRAP} flex-1 pb-24 pt-8` },
};

/** Hidden until a keyboard reaches it: the first stop on every page jumps past the bar. */
const SKIP_LINK =
  "sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-3 focus:z-50 focus:rounded focus:bg-rc-raised focus:px-3 focus:py-2 focus:font-mono focus:text-[11px] focus:uppercase focus:tracking-[0.18em] focus:text-rc-ink";

/**
 * The chrome around every route: a skip link, the top bar, the page and the
 * footer. It replaces the landing page's `NavShell` and the Race Control
 * sidebar shell: one top bar everywhere (PLAN, Locked decisions: Navigation).
 */
export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const layout = layoutFor(pathname);
  const frame = FRAME[layout];

  return (
    <div className={`flex flex-col ${frame.root}`}>
      <a href="#main" className={SKIP_LINK}>
        Skip to content
      </a>
      <SiteHeader pathname={pathname} />
      <main id="main" className={frame.main}>
        {children}
      </main>
      {layout === "workspace" ? null : <SiteFooter compact={layout === "page"} />}
    </div>
  );
}
