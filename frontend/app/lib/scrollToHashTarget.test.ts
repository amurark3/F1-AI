import { afterEach, describe, expect, it, vi } from "vitest";

import { scrollToHashTarget } from "./scrollToHashTarget";

function section(id: string): { node: HTMLElement; scroll: ReturnType<typeof vi.fn> } {
  const node = document.createElement("div");
  node.id = id;
  const scroll = vi.fn();
  node.scrollIntoView = scroll;
  return { node, scroll };
}

describe("scrollToHashTarget", () => {
  afterEach(() => {
    window.history.replaceState(null, "", "/");
  });

  it("scrolls to the element the URL's hash names", () => {
    window.history.replaceState(null, "", "/race-control/grand-prix?tab=predictions#predictions");
    const { node, scroll } = section("predictions");

    scrollToHashTarget(node);

    expect(scroll).toHaveBeenCalledWith({ block: "start" });
  });

  it("leaves the page where it is when the hash names something else", () => {
    window.history.replaceState(null, "", "/race-control/grand-prix#results");
    const { node, scroll } = section("predictions");

    scrollToHashTarget(node);

    expect(scroll).not.toHaveBeenCalled();
  });

  it("ignores the unmount call", () => {
    expect(() => scrollToHashTarget(null)).not.toThrow();
  });
});
