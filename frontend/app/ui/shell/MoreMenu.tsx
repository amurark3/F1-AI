"use client";

import { ChevronDown } from "lucide-react";
import Link from "next/link";
import { useCallback, useId, useRef, useState, type FocusEvent, type KeyboardEvent } from "react";
import { flushSync } from "react-dom";

import { focusables, moveFocus } from "./focus";
import { MORE_NAV, ariaCurrent, isMoreCurrent } from "./navConfig";
import { NAV_ITEM, NavUnderline, navTone } from "./navItem";
import { useDismiss, type DismissReason } from "./useDismiss";

/** Arrow keys walk the menu's links; from the trigger they open it first. */
const ARROWS: Partial<Record<string, 1 | -1>> = { ArrowDown: 1, ArrowUp: -1 };

/**
 * The top bar's "More ▾": a disclosure holding the reference screens
 * (Champions, Debriefs, Rulebook).
 *
 * The trigger is a button with `aria-expanded`; the panel is a plain list of
 * links, next to it in the tab order. Escape closes it and returns focus to
 * the trigger; a press outside, tabbing out of it, choosing a link or any
 * navigation closes it. ArrowDown and ArrowUp open it and walk its links. On
 * one of its screens the trigger carries the section's underline.
 */
export function MoreMenu({ pathname }: { pathname: string }) {
  const panelId = useId();
  const rootRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  // Open on the page it was opened on, so navigating anywhere closes it.
  const [openOn, setOpenOn] = useState<string | null>(null);
  const open = openOn === pathname;
  const current = isMoreCurrent(pathname);

  const close = useCallback(() => setOpenOn(null), []);
  const dismiss = useCallback((reason: DismissReason) => {
    setOpenOn(null);
    if (reason === "escape") triggerRef.current?.focus();
  }, []);
  useDismiss(open, rootRef, dismiss);

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    const delta = ARROWS[event.key];
    if (delta === undefined) return;
    event.preventDefault();
    // The panel must be showing before a link in it can take focus.
    if (!open) flushSync(() => setOpenOn(pathname));
    const links = focusables(event.currentTarget).filter((el) => el !== triggerRef.current);
    moveFocus(links, delta);
  };

  // Tabbing out closes it. A blur with no new focus (a press on nothing) is
  // left to the outside-press check, so a click on a link still lands.
  const onBlur = (event: FocusEvent<HTMLDivElement>) => {
    const next = event.relatedTarget;
    if (next !== null && !event.currentTarget.contains(next)) close();
  };

  return (
    // A presentation wrapper: it only hears the keys and focus moves of the button and links inside it.
    <div ref={rootRef} role="presentation" className="relative flex" onKeyDown={onKeyDown} onBlur={onBlur}>
      <button
        ref={triggerRef}
        type="button"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setOpenOn(open ? null : pathname)}
        className={`${NAV_ITEM} gap-1.5 ${navTone(current || open)}`}
      >
        More
        <ChevronDown aria-hidden="true" className={`size-3 ${open ? "rotate-180" : ""}`} />
        {current ? <NavUnderline /> : null}
      </button>
      <div
        id={panelId}
        hidden={!open}
        className="absolute -left-4 top-full z-10 mt-0.5 min-w-64 rounded-b-md border border-t-0 border-rc-line bg-rc-raised py-2 shadow-lg motion-safe:animate-overlay-in"
      >
        <ul>
          {MORE_NAV.map((link) => {
            const here = ariaCurrent(link, pathname);
            return (
              <li key={link.href}>
                <Link
                  href={link.href}
                  aria-current={here}
                  onClick={close}
                  className="group block px-4 py-2.5 focus-visible:-outline-offset-2"
                >
                  <span
                    className={`block font-mono text-[11px] font-medium uppercase leading-none tracking-[0.18em] ${navTone(here !== undefined)} group-hover:text-rc-ink`}
                  >
                    {link.label}
                  </span>
                  <span className="mt-1.5 block text-xs text-rc-ink-3">{link.description}</span>
                </Link>
              </li>
            );
          })}
        </ul>
      </div>
    </div>
  );
}
