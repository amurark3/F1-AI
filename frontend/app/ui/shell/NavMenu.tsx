"use client";

import { ChevronDown } from "lucide-react";
import Link from "next/link";
import { useCallback, useId, useRef, type FocusEvent, type KeyboardEvent } from "react";
import { flushSync } from "react-dom";

import { focusables, moveFocus } from "./focus";
import { ariaCurrent, type NavGroup } from "./navConfig";
import { NAV_ITEM, NavUnderline, navTone } from "./navItem";
import { useDismiss, type DismissReason } from "./useDismiss";

/** Arrow keys walk the menu's links; from the trigger they open it first. */
const ARROWS: Partial<Record<string, 1 | -1>> = { ArrowDown: 1, ArrowUp: -1 };

/**
 * The trigger is a button with `aria-expanded`; the panel is a plain list of
 * links, next to it in the tab order. Escape closes it and returns focus to
 * the trigger; a press outside, tabbing out of it, choosing a link or any
 * navigation closes it. ArrowDown and ArrowUp open it and walk its links. On
 * one of its screens the trigger carries the section's underline.
 */
export function NavMenu({
  group,
  pathname,
  open,
  onOpen,
}: {
  group: NavGroup;
  pathname: string;
  open: boolean;
  onOpen: (group: NavGroup["id"] | null) => void;
}) {
  const panelId = useId();
  const rootRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const current = group.links.some((link) => ariaCurrent(link, pathname));

  const close = useCallback(() => onOpen(null), [onOpen]);
  const dismiss = useCallback(
    (reason: DismissReason) => {
      close();
      if (reason === "escape") triggerRef.current?.focus();
    },
    [close],
  );
  useDismiss(open, rootRef, dismiss);

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    const delta = ARROWS[event.key];
    if (delta === undefined) return;
    event.preventDefault();
    // The panel must be showing before a link in it can take focus.
    if (!open) flushSync(() => onOpen(group.id));
    const links = focusables(event.currentTarget).filter((el) => el !== triggerRef.current);
    moveFocus(links, delta);
  };

  // Tabbing out closes it. A blur with no new focus (a press on nothing) is
  // left to the outside-press check, so a click on a link still lands.
  const onBlur = (event: FocusEvent<HTMLDivElement>) => {
    const next = event.relatedTarget;
    if (open && next !== null && !event.currentTarget.contains(next)) close();
  };

  return (
    // A presentation wrapper: it only hears the keys and focus moves of the button and links inside it.
    <div ref={rootRef} role="presentation" className="relative flex" onKeyDown={onKeyDown} onBlur={onBlur}>
      <button
        ref={triggerRef}
        type="button"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => onOpen(open ? null : group.id)}
        className={`${NAV_ITEM} gap-1.5 ${navTone(current || open)}`}
      >
        {group.label}
        <ChevronDown aria-hidden="true" className={`size-3 ${open ? "rotate-180" : ""}`} />
        {current ? <NavUnderline /> : null}
      </button>
      <div
        id={panelId}
        hidden={!open}
        className="absolute -left-4 top-full z-10 mt-0.5 w-[340px] rounded-b-md border border-t-0 border-rc-line bg-rc-raised p-2 shadow-lg motion-safe:animate-overlay-in"
      >
        <ul>
          {group.links.map((link) => {
            const here = ariaCurrent(link, pathname);
            return (
              <li key={link.href}>
                <Link
                  href={link.href}
                  aria-current={here}
                  onClick={close}
                  className="relative block rounded-sm px-3 py-2.5 hover:bg-rc-hero focus-visible:-outline-offset-2"
                >
                  {here && <span aria-hidden="true" className="absolute inset-y-2.5 left-0 w-0.5 bg-f1-red" />}
                  <span className="block text-sm font-semibold leading-tight text-rc-ink">{link.label}</span>
                  <span className="mt-1 block text-xs text-rc-ink-3">{link.description}</span>
                </Link>
              </li>
            );
          })}
        </ul>
      </div>
    </div>
  );
}
