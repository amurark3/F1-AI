import { readFileSync } from "node:fs";
import { join } from "node:path";

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import BrandLockup from "./BrandLockup";

/** The tab icon Next.js serves; the header mark must draw exactly this. */
const ICON_SVG = readFileSync(join(import.meta.dirname, "../icon.svg"), "utf8");

/** The mark's shapes in document order, as `tag` plus lowercased attributes. */
function shapes(svg: Element): Array<{ tag: string; attributes: Record<string, string> }> {
  return [...svg.children].map((shape) => ({
    tag: shape.tagName.toLowerCase(),
    attributes: Object.fromEntries([...shape.attributes].map(({ name, value }) => [name, value.toLowerCase()])),
  }));
}

function renderedMark(): Element {
  const { container } = render(<BrandLockup />);
  const mark = container.querySelector("svg");
  if (!mark) throw new Error("BrandLockup rendered no <svg> mark");
  return mark;
}

describe("BrandLockup", () => {
  it("reads as one image named F1 AI", () => {
    render(<BrandLockup />);
    const lockup = screen.getByRole("img", { name: "F1 AI" });
    expect(lockup).toHaveTextContent(/^F1AI$/);
  });

  it("sets the wordmark in the display face with the red square between F1 and AI", () => {
    render(<BrandLockup />);
    const wordmark = screen.getByRole("img", { name: "F1 AI" }).lastElementChild;
    expect(wordmark).toHaveClass("font-display", "text-rc-ink");
    expect([...(wordmark?.childNodes ?? [])].map((node) => node.textContent)).toEqual(["F1", "", "AI"]);
    expect(wordmark?.querySelector("span")).toHaveClass("bg-f1-red");
  });

  it("draws the same mark as app/icon.svg, from the tokens", () => {
    const icon = new DOMParser().parseFromString(ICON_SVG, "image/svg+xml").documentElement;
    const mark = renderedMark();
    expect(mark.getAttribute("viewBox")).toBe(icon.getAttribute("viewBox"));
    expect(shapes(mark)).toEqual(shapes(icon));
  });

  it("hides the mark from assistive tech, since the lockup carries the name", () => {
    expect(renderedMark()).toHaveAttribute("aria-hidden", "true");
  });
});
