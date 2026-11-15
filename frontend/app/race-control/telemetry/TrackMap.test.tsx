import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { TrackMap } from "./TrackMap";

const X = [0, 1000, 1000, 0, 0, 500];
const Y = [0, 0, 1000, 1000, 100, 100];

function renderMap(extra: Partial<Parameters<typeof TrackMap>[0]> = {}) {
  render(<TrackMap x={X} y={Y} colourAt={() => "#123456"} readout={() => "reading"} ariaLabel="A lap" {...extra} />);
  return screen.getByRole("img", { name: "A lap" });
}

describe("TrackMap", () => {
  it("draws one segment per sample and needs no corners or markers", () => {
    const map = renderMap();
    expect(map.querySelectorAll("g[mask] line")).toHaveLength(X.length - 1);
    expect(map.querySelector("text")).toBeNull();
  });

  it("dashes the segments a second encoding picks out", () => {
    const map = renderMap({ dashedAt: (index) => index === 0 });
    const lines = map.querySelectorAll("g[mask] line");
    expect(lines[0]).toHaveAttribute("stroke-dasharray");
    expect(lines[1]).not.toHaveAttribute("stroke-dasharray");
  });

  it("numbers the corners, with a leader line when the number is moved off its apex", () => {
    // Ten numbers on one apex cannot all sit beside it.
    const corners = Array.from({ length: 10 }, (_, index) => ({
      number: index + 1,
      label: String(index + 1),
      x: 1000,
      y: 500,
      angle: 0,
    }));
    const map = renderMap({ corners });
    expect(map.querySelectorAll("text")).toHaveLength(10);
    expect(map.querySelectorAll("line:not(g[mask] line)").length).toBeGreaterThan(0);
  });
});
