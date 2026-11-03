import { render, screen } from "@testing-library/react";
import { useReducedMotion } from "framer-motion";
import { renderToString } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

import { CircuitMap } from "./CircuitMap";
import { outlinePath, type CircuitMapData } from "./outlinePath";
import { f1, rc } from "./tokens";

import type * as FramerMotion from "framer-motion";

vi.mock("framer-motion", async (importOriginal) => ({
  ...(await importOriginal<typeof FramerMotion>()),
  useReducedMotion: vi.fn(),
}));

const MAP: CircuitMapData = {
  source: "multiviewer",
  season: 2026,
  width: 840,
  height: 420,
  points: [
    [40, 40],
    [800, 40],
    [800, 380],
    [40, 380],
  ],
  corners: [
    { label: "1", x: 800, y: 40, label_x: 820, label_y: 30 },
    { label: "2", x: 800, y: 380, label_x: 820, label_y: 395 },
  ],
};

function lappingMarkers(container: Element): number {
  return container.getElementsByTagName("animateMotion").length;
}

describe("CircuitMap", () => {
  it("draws the outline as a named image, with its corner numbers", () => {
    vi.mocked(useReducedMotion).mockReturnValue(true);
    const { container } = render(<CircuitMap map={MAP} name="Interlagos" />);

    const svg = screen.getByRole("img", { name: "Interlagos layout" });
    expect(svg).toHaveAttribute("viewBox", "0 0 840 420");
    const paths = [...container.querySelectorAll("path")];
    expect(paths).toHaveLength(3);
    for (const path of paths) expect(path).toHaveAttribute("d", outlinePath(MAP));
    expect(paths[0]).toHaveAttribute("stroke", f1.red);
    expect(paths[2]).toHaveClass("motion-safe:animate-track-draw");

    const labels = screen.getAllByText(/^\d$/);
    expect(labels.map((label) => label.textContent)).toEqual(["1", "2"]);
    expect(labels[0]).toHaveAttribute("fill", rc.ink3);
    expect(labels[1]).toHaveAttribute("x", "820");
    // Each number settles in 50 ms after the one before, once the line has drawn.
    expect(labels[0]).toHaveStyle({ animationDelay: "1.6s" });
    expect(labels[1].getAttribute("style")).toMatch(/animation-delay: 1\.65\d*s/);
    expect(labels[0].parentElement).toHaveAttribute("font-size", String(840 / 42));
  });

  it("laps a marker round the outline once hydrated, for a reader who allows motion", () => {
    vi.mocked(useReducedMotion).mockReturnValue(false);
    const { container } = render(<CircuitMap map={MAP} name="Interlagos" />);

    expect(lappingMarkers(container)).toBe(2);
    const track = container.querySelector("path[id]");
    for (const mpath of container.getElementsByTagName("mpath")) {
      expect(mpath).toHaveAttribute("href", `#${track?.id}`);
    }
    expect(container.querySelector("g > path")).toHaveAttribute("stroke", rc.redText);
  });

  it.each([
    ["prefers reduced motion", true],
    ["has not reported a preference", null],
  ])("keeps the marker still for a reader who %s", (_case, reduce) => {
    vi.mocked(useReducedMotion).mockReturnValue(reduce);
    const { container } = render(<CircuitMap map={MAP} name="Interlagos" />);

    expect(lappingMarkers(container)).toBe(0);
  });

  it("leaves the marker out of the server render, which cannot know the preference", () => {
    vi.mocked(useReducedMotion).mockReturnValue(false);
    const html = renderToString(<CircuitMap map={MAP} name="Interlagos" />);

    expect(html).toContain('aria-label="Interlagos layout"');
    expect(html).not.toContain("animateMotion");
  });
});
