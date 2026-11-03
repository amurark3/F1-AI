import { readFileSync } from "node:fs";
import { join } from "node:path";

import { render } from "@testing-library/react";
import { CartesianGrid, Line, LineChart, ReferenceLine, Tooltip, XAxis, YAxis } from "recharts";
import { describe, expect, it } from "vitest";

import { chartTheme } from "./chartTheme";
import { f1, font, rc } from "./tokens";

const DATA = [
  { round: "R1", points: 25 },
  { round: "R2", points: 43 },
  { round: "R3", points: 68 },
];

describe("chartTheme", () => {
  it("takes every colour from the tokens, never a literal", () => {
    const source = readFileSync(join(import.meta.dirname, "chartTheme.ts"), "utf8");
    expect(source).not.toMatch(/#[\da-f]{3,8}\b|rgba?\(/i);
  });

  it("sets ticks in Geist Mono 500 at 10 px in the tertiary ink, with no axis or tick lines", () => {
    expect(chartTheme.axis).toEqual({
      tick: { fill: rc.ink3, fontFamily: font.mono, fontSize: 10, fontWeight: 500 },
      axisLine: false,
      tickLine: false,
    });
  });

  it("draws the grid and hover cursors as faint ink, and rules in the fill-and-rule red", () => {
    expect(chartTheme.grid).toEqual({ stroke: rc.ink, strokeOpacity: 0.06 });
    expect(chartTheme.tooltip.cursor).toEqual({ stroke: rc.ink, strokeOpacity: 0.12 });
    expect(chartTheme.barCursor).toEqual({ fill: rc.ink, fillOpacity: 0.04 });
    expect(chartTheme.rule).toEqual({ stroke: f1.red, strokeWidth: 2 });
  });

  it("puts tooltips on the raised surface with a hairline border", () => {
    expect(chartTheme.tooltip.contentStyle).toMatchObject({
      background: rc.raised,
      border: `1px solid ${rc.line}`,
      color: rc.ink,
      fontFamily: font.sans,
    });
    expect(chartTheme.tooltip.labelStyle.color).toBe(rc.ink);
    expect(chartTheme.tooltip.itemStyle.color).toBe(rc.ink2);
  });

  it("spreads straight onto Recharts parts", () => {
    const { container } = render(
      <LineChart width={400} height={200} data={DATA}>
        <CartesianGrid {...chartTheme.grid} vertical={false} />
        <XAxis dataKey="round" {...chartTheme.axis} />
        <YAxis {...chartTheme.axis} />
        <Tooltip {...chartTheme.tooltip} />
        <ReferenceLine y={50} {...chartTheme.rule} />
        <Line dataKey="points" isAnimationActive={false} />
      </LineChart>,
    );

    const tick = container.querySelector(".recharts-xAxis-tick-labels .recharts-cartesian-axis-tick-value");
    expect(tick).toHaveAttribute("fill", rc.ink3);
    expect(tick).toHaveAttribute("font-family", font.mono);
    expect(container.querySelector(".recharts-cartesian-axis-line")).toBeNull();
    expect(container.querySelector(".recharts-cartesian-grid-horizontal line")).toHaveAttribute(
      "stroke-opacity",
      "0.06",
    );
    expect(container.querySelector(".recharts-reference-line-line")).toHaveAttribute("stroke", f1.red);
  });

  it("styles hand-drawn SVG with the same objects", () => {
    const { container } = render(
      <svg>
        <line {...chartTheme.grid} x1={0} x2={100} y1={10} y2={10} />
        <text {...chartTheme.axis.tick}>100</text>
      </svg>,
    );

    expect(container.querySelector("line")).toHaveAttribute("stroke", rc.ink);
    expect(container.querySelector("text")).toHaveAttribute("font-size", "10");
  });
});
