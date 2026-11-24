"use client";

import Link from "next/link";

import { useServerStatus } from "@/app/hooks/useServerStatus";
import { noticePhase } from "@/app/lib/serverStatus";

import BrandLockup from "../BrandLockup";

import { MobileNav } from "./MobileNav";
import { showsRaceStatus } from "./navConfig";
import { RaceStatusChip } from "./RaceStatusChip";
import { SiteNav } from "./SiteNav";
import { WarmupLights } from "./WarmupLights";
import { WRAP } from "./wrap";

/**
 * The bar's status slot, right of the links. Normally it holds the race status
 * chip on data routes and stays empty on static ones (`/`, nothing fetched), and
 * it is too narrow on a phone, where `MobileNav` carries the chip. While the
 * backend restarts or can't be reached, the restart lights take the slot over
 * on every route and every width: the one thing that shows in the phone bar.
 */
function StatusSlot({ pathname }: { pathname: string }) {
  const server = useServerStatus();
  const phase = noticePhase(server);

  if (phase) {
    return (
      <div className="flex">
        <WarmupLights phase={phase} server={server} />
      </div>
    );
  }
  return <div className="hidden sm:flex">{showsRaceStatus(pathname) ? <RaceStatusChip /> : null}</div>;
}

/**
 * The one top bar on every screen (the mockups' `.topbar`): the B1 lockup
 * home, the section links (or MENU below `lg`), the status slot, and the red
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
