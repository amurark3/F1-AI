"use client";

import { useEffect, type RefObject } from "react";

/** Why a menu is closing: Escape returns focus to its trigger, a press outside leaves it where it landed. */
export type DismissReason = "escape" | "outside";

/**
 * While `open`, calls `onDismiss` when Escape is pressed anywhere or a press
 * lands outside `container`. Pass a stable `onDismiss` (`useCallback`), or the
 * listeners re-attach on every render.
 */
export function useDismiss(
  open: boolean,
  container: RefObject<HTMLElement | null>,
  onDismiss: (reason: DismissReason) => void,
): void {
  useEffect(() => {
    if (!open) return undefined;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onDismiss("escape");
    };
    const onPointerDown = (event: PointerEvent) => {
      // Listening on `document`, every target is a node.
      if (container.current?.contains(event.target as Node)) return;
      onDismiss("outside");
    };
    document.addEventListener("keydown", onKeyDown);
    document.addEventListener("pointerdown", onPointerDown);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      document.removeEventListener("pointerdown", onPointerDown);
    };
  }, [open, container, onDismiss]);
}
