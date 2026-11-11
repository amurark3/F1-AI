"use client";

import Link from "next/link";
import { useCallback, useRef, useState, type KeyboardEvent } from "react";

import { useScrollLock } from "@/app/hooks/useScrollLock";

import BrandLockup from "../BrandLockup";
import { EYEBROW } from "../typography";

import { trapTab } from "./focus";
import { MORE_NAV, PRIMARY_NAV, ariaCurrent, showsRaceStatus, type NavLink } from "./navConfig";
import { RaceStatusChip } from "./RaceStatusChip";
import { WRAP } from "./wrap";

/** The mockups' `.menu-btn`: a hairline box in mono caps. Its counterpart in the menu reads "Close". */
const MENU_BUTTON =
  "rounded border border-rc-line px-3 py-[9px] font-mono text-[11px] font-semibold uppercase leading-none tracking-[0.18em] text-rc-ink-2 transition-colors hover:text-rc-ink";

const pad = (n: number) => String(n).padStart(2, "0");

interface MenuListProps {
  links: readonly NavLink[];
  pathname: string;
  /** The index numeral of the first row, so More's rows carry on from the main list. */
  first: number;
  onNavigate: () => void;
}

/** Rows in the index style (`docs/design/redesign/index.html`): a mono numeral, then the title in the display face. */
function MenuList({ links, pathname, first, onNavigate }: MenuListProps) {
  return (
    <ol className="border-t border-rc-line">
      {links.map((link, i) => {
        const here = ariaCurrent(link, pathname);
        return (
          <li key={link.href} className="border-b border-rc-line">
            <Link
              href={link.href}
              aria-current={here}
              onClick={onNavigate}
              className="group grid grid-cols-[40px_1fr] items-baseline py-4"
            >
              <span className={`font-mono text-xs font-semibold ${here ? "text-rc-red-text" : "text-rc-ink-3"}`}>
                {pad(first + i)}
              </span>
              <span
                className={`font-display text-[28px] font-extrabold uppercase leading-none ${here ? "text-rc-ink" : "text-rc-ink-2 group-hover:text-rc-ink"}`}
              >
                {link.label}
              </span>
            </Link>
          </li>
        );
      })}
    </ol>
  );
}

/**
 * The top bar below `xl`: a MENU button that opens every section as a
 * full-screen modal menu.
 *
 * The menu is a `dialog` that repeats the bar's top row (logo, then "Close"
 * where "Menu" was), so the bar seems to stay put. Focus starts on Close and
 * Tab cycles inside it; Escape or Close shuts it and returns focus to MENU.
 * The page behind it cannot scroll. Choosing a link or any navigation closes
 * it. On data routes it also carries the race status, which the bar has no
 * room for on a phone.
 */
export function MobileNav({ pathname }: { pathname: string }) {
  const triggerRef = useRef<HTMLButtonElement>(null);
  // Open on the page it was opened on, so navigating anywhere closes it.
  const [openOn, setOpenOn] = useState<string | null>(null);
  const open = openOn === pathname;
  useScrollLock(open);

  const close = useCallback(() => setOpenOn(null), []);
  const closeToTrigger = () => {
    setOpenOn(null);
    triggerRef.current?.focus();
  };

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === "Escape") closeToTrigger();
    else if (event.key === "Tab" && trapTab(event.currentTarget, event.shiftKey)) event.preventDefault();
  };

  return (
    <>
      <button
        ref={triggerRef}
        type="button"
        aria-haspopup="dialog"
        aria-expanded={open}
        onClick={() => setOpenOn(pathname)}
        className={`${MENU_BUTTON} xl:hidden`}
      >
        Menu
      </button>
      {open ? (
        <div
          role="dialog"
          aria-modal="true"
          aria-label="Site menu"
          className="fixed inset-0 z-50 overflow-y-auto overscroll-contain bg-background motion-safe:animate-overlay-in"
        >
          {/* A presentation wrapper: it only hears the keys of the controls inside it. */}
          <div role="presentation" onKeyDown={onKeyDown}>
            <div className="border-b border-rc-line">
              <div className={`${WRAP} flex h-15 items-center justify-between gap-4`}>
                <Link href="/" aria-label="F1 AI home" onClick={close} className="shrink-0">
                  <BrandLockup />
                </Link>
                <button type="button" autoFocus onClick={closeToTrigger} className={MENU_BUTTON}>
                  Close
                </button>
              </div>
              <div aria-hidden="true" className="h-0.5 bg-f1-red" />
            </div>
            <nav aria-label="Main" className={`${WRAP} pb-16 pt-6`}>
              {showsRaceStatus(pathname) ? (
                <div className="mb-6 flex">
                  <RaceStatusChip />
                </div>
              ) : null}
              <MenuList links={PRIMARY_NAV} pathname={pathname} first={1} onNavigate={close} />
              <p className={`${EYEBROW} mb-3 mt-10`}>More</p>
              <MenuList links={MORE_NAV} pathname={pathname} first={PRIMARY_NAV.length + 1} onNavigate={close} />
            </nav>
          </div>
        </div>
      ) : null}
    </>
  );
}
