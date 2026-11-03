"use client";

import { useCallback, useEffect, useId, useRef, useState, type ButtonHTMLAttributes, type ReactNode } from "react";
import { createPortal } from "react-dom";

import { useIsHydrated } from "@/app/components/LocalTime";

import { placeTooltip, type TooltipPlacement } from "./placeTooltip";

/** Grace for the pointer to cross the gap from the trigger onto the tooltip. */
const CLOSE_DELAY_MS = 120;

type HandledProps = "children" | "type" | "onClick" | "onFocus" | "onBlur" | "onPointerEnter" | "onPointerLeave";

interface TooltipProps extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, HandledProps> {
  /** What the trigger button shows. */
  label: ReactNode;
  /** What the tooltip says; phrasing content only, since a trigger often sits in a paragraph. */
  children: ReactNode;
}

/**
 * A button that explains itself: its tooltip opens on hover and keyboard
 * focus, pins open on a click (the only way in on a touch screen), and closes
 * on Escape, blur, a press elsewhere, scroll or resize. The pointer can cross
 * onto the tooltip without losing it.
 *
 * The tooltip is portalled to `<body>` with fixed offsets, so a panel's
 * `overflow: hidden` never clips it. It renders only after hydration (the
 * server has no `document`), and stays mounted while hidden so it always
 * describes the trigger (`aria-describedby`).
 */
export function Tooltip({ label, children, className = "", ...buttonProps }: TooltipProps) {
  const tipId = useId();
  const hydrated = useIsHydrated();
  const closeTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const [hovered, setHovered] = useState(false);
  const [pinned, setPinned] = useState(false);
  const [placement, setPlacement] = useState<TooltipPlacement>({});
  const open = hovered || pinned;

  const cancelClose = useCallback(() => clearTimeout(closeTimer.current), []);
  const dismiss = useCallback(() => {
    cancelClose();
    setHovered(false);
    setPinned(false);
  }, [cancelClose]);
  const closeSoon = () => {
    cancelClose();
    closeTimer.current = setTimeout(() => setHovered(false), CLOSE_DELAY_MS);
  };
  const keepOpen = () => {
    cancelClose();
    setHovered(true);
  };
  const place = (trigger: HTMLElement) =>
    setPlacement(
      placeTooltip(trigger.getBoundingClientRect(), { width: window.innerWidth, height: window.innerHeight }),
    );
  const openAt = (trigger: HTMLElement) => {
    place(trigger);
    keepOpen();
  };

  useEffect(() => cancelClose, [cancelClose]);
  useDismissal(open, tipId, dismiss);

  return (
    <>
      <button
        type="button"
        aria-describedby={tipId}
        data-tooltip-owner={tipId}
        onPointerEnter={(event) => openAt(event.currentTarget)}
        onPointerLeave={closeSoon}
        onFocus={(event) => openAt(event.currentTarget)}
        onBlur={dismiss}
        onClick={(event) => {
          place(event.currentTarget);
          setPinned((current) => !current);
        }}
        className={`cursor-help focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-rc-red-text ${className}`}
        {...buttonProps}
      >
        {label}
      </button>
      {hydrated
        ? createPortal(
            <span
              role="tooltip"
              id={tipId}
              data-tooltip-owner={tipId}
              data-state={open ? "open" : "closed"}
              onPointerEnter={keepOpen}
              onPointerLeave={closeSoon}
              style={placement}
              className={`${open ? "visible" : "invisible"} fixed z-50 w-max max-w-xs rounded border border-rc-line bg-rc-raised px-3 py-2.5 text-left font-sans text-xs leading-normal text-rc-ink-2 shadow-lg`}
            >
              {children}
            </span>,
            document.body,
          )
        : null}
    </>
  );
}

/** While open: Escape anywhere, a press outside trigger and tooltip, scroll or resize close it. */
function useDismissal(open: boolean, tipId: string, dismiss: () => void): void {
  useEffect(() => {
    if (!open) return undefined;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") dismiss();
    };
    const onPointerDown = (event: PointerEvent) => {
      const { target } = event;
      if (!(target instanceof Element) || !target.closest(`[data-tooltip-owner="${tipId}"]`)) dismiss();
    };
    document.addEventListener("keydown", onKeyDown);
    document.addEventListener("pointerdown", onPointerDown);
    window.addEventListener("scroll", dismiss, true);
    window.addEventListener("resize", dismiss);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      document.removeEventListener("pointerdown", onPointerDown);
      window.removeEventListener("scroll", dismiss, true);
      window.removeEventListener("resize", dismiss);
    };
  }, [open, tipId, dismiss]);
}
