/**
 * A ref callback that scrolls its element into view when the URL's hash names
 * it. Sections that render once their data arrives mount too late for the
 * browser's own jump to `#id`.
 */
export function scrollToHashTarget(node: HTMLElement | null): void {
  if (node && window.location.hash === `#${node.id}`) {
    node.scrollIntoView({ block: "start" });
  }
}
