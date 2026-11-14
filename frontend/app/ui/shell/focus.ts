/**
 * Keyboard focus helpers for the shell's menus. Plain DOM, no React.
 */

/** What the menus hold that a keyboard can reach: links and enabled buttons. */
const FOCUSABLE = "a[href], button:not([disabled])";

/** Index `delta` steps from `index`, wrapping round a list of `count`. */
export function wrapIndex(index: number, delta: number, count: number): number {
  return (((index + delta) % count) + count) % count;
}

/** The reachable controls inside `root`, in document order, skipping any in a `hidden` subtree. */
export function focusables(root: HTMLElement): HTMLElement[] {
  return Array.from(root.querySelectorAll<HTMLElement>(FOCUSABLE)).filter((el) => el.closest("[hidden]") === null);
}

/**
 * Moves focus one step through `items` from the focused one, wrapping round.
 * From outside the list, a step forward lands on the first item and a step
 * back on the last (how a menu answers ArrowDown and ArrowUp).
 */
export function moveFocus(items: readonly HTMLElement[], delta: 1 | -1): void {
  if (items.length === 0) return;
  const current = items.findIndex((item) => item === document.activeElement);
  // Just before the first item going forward, the first item itself going back.
  const outside = delta === 1 ? -1 : 0;
  const start = current === -1 ? outside : current;
  items[wrapIndex(start, delta, items.length)]?.focus();
}

/**
 * Keeps Tab inside `root` (a modal menu): Tab on its last control returns to
 * the first, Shift+Tab on the first goes round to the last. Returns true when
 * it moved focus, so the caller cancels the browser's own move.
 */
export function trapTab(root: HTMLElement, backwards: boolean): boolean {
  const items = focusables(root);
  const first = items[0];
  const last = items.at(-1);
  if (first === undefined || last === undefined) return false;
  const edge = backwards ? first : last;
  if (document.activeElement !== edge) return false;
  (backwards ? last : first).focus();
  return true;
}
