"use client";

import { MotionConfig } from "framer-motion";
import Link from "next/link";

import { MoreMenu } from "./MoreMenu";
import { PRIMARY_NAV, ariaCurrent } from "./navConfig";
import { NAV_ITEM, NavUnderline, navTone } from "./navItem";

/**
 * The top bar's links on wide screens (from `xl`; below that, `MobileNav`).
 * Seven sections then "More", each in mono caps; the current section reads
 * in the primary tone, carries `aria-current` and the sliding red underline.
 */
export function SiteNav({ pathname }: { pathname: string }) {
  return (
    <MotionConfig reducedMotion="user">
      <nav aria-label="Main" className="hidden flex-1 self-stretch xl:flex">
        <ul className="flex gap-6.5">
          {PRIMARY_NAV.map((link) => {
            const here = ariaCurrent(link, pathname);
            return (
              <li key={link.href} className="flex">
                <Link href={link.href} aria-current={here} className={`${NAV_ITEM} ${navTone(here !== undefined)}`}>
                  {link.label}
                  {here ? <NavUnderline /> : null}
                </Link>
              </li>
            );
          })}
          <li className="flex">
            <MoreMenu pathname={pathname} />
          </li>
        </ul>
      </nav>
    </MotionConfig>
  );
}
