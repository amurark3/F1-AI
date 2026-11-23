"use client";

import { MotionConfig } from "framer-motion";
import Link from "next/link";
import { useState } from "react";

import { ariaCurrent, COMMAND_CENTER_LINK, ENGINEER_LINK, NAV_GROUPS, type NavGroup, type NavLink } from "./navConfig";
import { NAV_ITEM, NavUnderline, navTone } from "./navItem";
import { NavMenu } from "./NavMenu";

function TopLink({ link, pathname, boxed = false }: { link: NavLink; pathname: string; boxed?: boolean }) {
  const here = ariaCurrent(link, pathname);
  return (
    <Link href={link.href} aria-current={here} className={`${NAV_ITEM} ${navTone(here !== undefined)}`}>
      {boxed ? (
        <span className="rounded border border-rc-line px-3.5 py-2.5 text-rc-ink hover:border-rc-ink-3">
          {link.label}
        </span>
      ) : (
        link.label
      )}
      {here && <NavUnderline />}
    </Link>
  );
}

function NavItems({ pathname }: { pathname: string }) {
  const [openGroup, setOpenGroup] = useState<NavGroup["id"] | null>(null);

  return (
    <ul className="flex flex-1 gap-7">
      <li className="flex">
        <TopLink link={COMMAND_CENTER_LINK} pathname={pathname} />
      </li>
      {NAV_GROUPS.map((group) => (
        <li key={group.id} className="flex">
          <NavMenu group={group} pathname={pathname} open={openGroup === group.id} onOpen={setOpenGroup} />
        </li>
      ))}
      <li className="ml-auto flex">
        <TopLink link={ENGINEER_LINK} pathname={pathname} boxed />
      </li>
    </ul>
  );
}

/** At desktop widths the groups are disclosures, and navigation resets the open group. */
export function SiteNav({ pathname }: { pathname: string }) {
  return (
    <MotionConfig reducedMotion="user">
      <nav aria-label="Main" className="hidden flex-1 self-stretch lg:flex">
        <NavItems key={pathname} pathname={pathname} />
      </nav>
    </MotionConfig>
  );
}
