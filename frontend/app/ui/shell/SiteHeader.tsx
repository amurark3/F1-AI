"use client";

import Link from "next/link";

import BrandLockup from "../BrandLockup";

import { MobileNav } from "./MobileNav";
import { showsRaceStatus } from "./navConfig";
import { RaceStatusChip } from "./RaceStatusChip";
import { SiteNav } from "./SiteNav";
import { WRAP } from "./wrap";

/**
 * The bar's status slot, right of the links. On data routes it holds the race
 * status chip; on static routes (`/`) it stays empty and nothing is fetched.
 * P3.5's restart lights take the slot over, on every route, while the
 * backend restarts. Too narrow on a phone, where `MobileNav` carries the chip.
 */
function StatusSlot({ pathname }: { pathname: string }) {
  return <div className="hidden sm:flex">{showsRaceStatus(pathname) ? <RaceStatusChip /> : null}</div>;
}

/**
 * The one top bar on every screen (the mockups' `.topbar`): the B1 lockup
 * home, the section links (or MENU below `xl`), the status slot, and the red
 * streak along its foot. It sticks to the top as the page scrolls.
 */
export function SiteHeader({ pathname }: { pathname: string }) {
  return (
    <header className="sticky top-0 z-40 border-b border-rc-line bg-background/94">
      <div className={`${WRAP} flex h-15 items-center gap-10`}>
        <Link href="/" aria-label="F1 AI home" className="shrink-0">
          <BrandLockup />
        </Link>
        <SiteNav pathname={pathname} />
        <div className="ml-auto flex items-center gap-4">
          <StatusSlot pathname={pathname} />
          <MobileNav pathname={pathname} />
        </div>
      </div>
      <div aria-hidden="true" className="h-0.5 bg-f1-red" />
    </header>
  );
}
