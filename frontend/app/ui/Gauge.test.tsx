import { render, screen } from "@testing-library/react";
import { renderToString } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { Gauge } from "./Gauge";
import { GAUGE_PATH_LENGTH } from "./gaugeArc";
import { f1, rc } from "./tokens";

function arcOf(meter: HTMLElement): SVGCircleElement | null {
  return meter.querySelector("[data-arc]");
}

describe("Gauge", () => {
  it("is a meter named by its label that reads its value on the range", () => {
    // Model scorecard (gp-predictions.html): podium places right 62%.
    render(<Gauge value={62} label="Podium places right" />);

    const meter = screen.getByRole("meter", { name: "Podium places right" });
    expect(meter).toHaveAttribute("aria-valuenow", "62");
    expect(meter).toHaveAttribute("aria-valuemin", "0");
    expect(meter).toHaveAttribute("aria-valuemax", "100");
    expect(meter).toHaveAttribute("aria-valuetext", "62%");
  });

  it("writes the value inside the ring and the label under it, so the ring is never the only reading", () => {
    render(<Gauge value={50} label="Winner right" />);

    const value = screen.getByText("50%");
    expect(value.tagName.toLowerCase()).toBe("text");
    expect(value).toHaveClass("font-display", "font-extrabold", "fill-rc-ink");
    expect(screen.getByText("Winner right")).toHaveClass("font-mono", "uppercase", "text-rc-ink-3");
  });

  it("fills the red arc from the top by the value's share, over the hairline track", () => {
    render(<Gauge value={79} label="Top-ten right" />);

    const meter = screen.getByRole("meter");
    const [track] = meter.querySelectorAll("circle");
    expect(track).toHaveAttribute("stroke", rc.line);

    const arc = arcOf(meter);
    expect(arc).toHaveAttribute("stroke", f1.red);
    expect(arc).toHaveAttribute("pathLength", String(GAUGE_PATH_LENGTH));
    expect(arc).toHaveAttribute("stroke-dasharray", "100 100");
    expect(Number(arc?.getAttribute("stroke-dashoffset"))).toBeCloseTo(21);
    expect(arc).toHaveAttribute("transform", "rotate(-90 40 40)");
    expect(meter.querySelector("svg")).toHaveAttribute("aria-hidden", "true");
  });

  it("reads a count against its own range in the caller's words and colour", () => {
    render(<Gauge value={7} min={0} max={19} valueText="7/19" label="Podiums" color="#e8002d" />);

    const meter = screen.getByRole("meter", { name: "Podiums" });
    expect(meter).toHaveAttribute("aria-valuemax", "19");
    expect(meter).toHaveAttribute("aria-valuetext", "7/19");
    expect(screen.getByText("7/19")).toBeInTheDocument();
    expect(arcOf(meter)).toHaveAttribute("stroke", "#e8002d");
  });

  it("writes its own share when no figure is given, and keeps aria-valuenow on the range", () => {
    render(<Gauge value={12} max={10} label="Over the top" />);

    const meter = screen.getByRole("meter");
    expect(meter).toHaveAttribute("aria-valuetext", "120%");
    expect(meter).toHaveAttribute("aria-valuenow", "10");
    expect(arcOf(meter)).toHaveAttribute("stroke-dashoffset", "0");
  });

  it("draws no arc for a zero, so a round cap never paints a dot", () => {
    render(<Gauge value={0} label="Exact position right" />);
    expect(screen.getByRole("meter")).toHaveAttribute("aria-valuetext", "0%");
    expect(arcOf(screen.getByRole("meter"))).toBeNull();
  });

  it("shows a dash and says so for a missing value, rather than an empty ring that reads as zero", () => {
    render(<Gauge value={null} valueText="62%" label="Winner right" />);

    expect(screen.queryByRole("meter")).toBeNull();
    const figure = screen.getByRole("img", { name: "Winner right: no data" });
    expect(screen.getByText("—")).toBeInTheDocument();
    expect(arcOf(figure)).toBeNull();
  });

  it("fills in once behind motion-safe, so the server's HTML is the gauge at rest", () => {
    const html = renderToString(<Gauge value={62} label="Podium places right" className="w-24" />);
    expect(html).toContain("motion-safe:animate-gauge-fill");
    expect(html).not.toMatch(/(^|[\s"])animate-/);
    expect(html).toContain("w-24");
  });
});
