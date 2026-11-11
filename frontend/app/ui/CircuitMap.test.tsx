import { render, screen } from "@testing-library/react";
import { useReducedMotion } from "framer-motion";
import { renderToString } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

import { SAO_PAULO_2026 } from "@/test/fixtures";

import { CircuitMap } from "./CircuitMap";
import { LABEL_HALO_EM } from "./cornerLabels";
import { circuitCornerLabels, outlinePath, type CircuitMapData } from "./outlinePath";
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
    { label: "1", x: 800, y: 40, angle: 315 },
    { label: "2", x: 800, y: 380, angle: 45 },
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
    // Each number sits where the placement put it, on a halo of the hero band.
    const placed = circuitCornerLabels(MAP);
    expect(labels.map((label) => [label.getAttribute("x"), label.getAttribute("y")])).toEqual(
      placed.map((corner) => [String(corner.x), String(corner.y)]),
    );
    expect(labels[0]).toHaveAttribute("stroke", rc.hero);
    expect(labels[0]).toHaveAttribute("paint-order", "stroke");
    expect(labels[0]).toHaveAttribute("stroke-width", String((840 / 42) * LABEL_HALO_EM));
    // Each number settles in 50 ms after the one before, once the line has drawn.
    expect(labels[0].parentElement).toHaveStyle({ animationDelay: "1.6s" });
    expect(labels[1].parentElement?.getAttribute("style")).toMatch(/animation-delay: 1\.65\d*s/);
    expect(labels[0].parentElement?.parentElement).toHaveAttribute("font-size", String(840 / 42));
    // Both clear the track beside their apex, so neither needs a leader.
    expect(container.querySelectorAll("line")).toHaveLength(0);
  });

  it("draws a leader to a number that had to move out from its apex", () => {
    vi.mocked(useReducedMotion).mockReturnValue(true);
    const map = SAO_PAULO_2026.circuit.map;
    if (map === null) throw new Error("the São Paulo fixture has a map");
    const { container } = render(<CircuitMap map={map} name="Interlagos" />);

    const withLeader = circuitCornerLabels(map).filter((corner) => corner.leader !== null);
    expect(withLeader.map((corner) => corner.label)).toEqual(["10"]);
    const lines = [...container.querySelectorAll("line")];
    expect(lines).toHaveLength(1);
    expect(lines[0]).toHaveAttribute("stroke", rc.dim);
    expect(lines[0]).toHaveAttribute("x1", String(withLeader[0].leader?.x1));
    expect(lines[0].parentElement).toHaveTextContent("10");
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
