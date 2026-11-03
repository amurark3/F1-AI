import { render } from "@testing-library/react";
import { cloneElement, isValidElement, type ComponentProps, type ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

import { f1, rc } from "@/app/ui/tokens";

import { ModelAttributionBars } from "./Charts";

import type * as Recharts from "recharts";

// jsdom has no layout, so the responsive wrapper would measure 0 × 0 and draw
// nothing: hand the chart a fixed size. Bars grow in from zero over animation
// frames jsdom never paints, so they are drawn at rest.
vi.mock("recharts", async (importOriginal) => {
  const recharts = await importOriginal<typeof Recharts>();
  const { Bar } = recharts;
  return {
    ...recharts,
    Bar: (props: ComponentProps<typeof Bar>) => <Bar {...props} isAnimationActive={false} />,
    ResponsiveContainer: ({ children }: { children: ReactNode }) =>
      isValidElement<{ width?: number; height?: number }>(children)
        ? cloneElement(children, { width: 480, height: 200 })
        : null,
  };
});

describe("ModelAttributionBars", () => {
  it("paints places gained in the gain token and places lost in red text, never DRS green", () => {
    const { container } = render(
      <ModelAttributionBars
        data={[
          { label: "Grid position", contribution: -1.8 },
          { label: "Title lead", contribution: -0.6 },
          { label: "DNF risk", contribution: 0.4 },
        ]}
      />,
    );

    const fills = Array.from(container.querySelectorAll(".recharts-bar-rectangle path"), (bar) =>
      bar.getAttribute("fill"),
    );
    expect(fills).toEqual([rc.gain, rc.gain, rc.redText]);
    expect(container.innerHTML.toLowerCase()).not.toContain(f1.drs);
  });

  it("draws nothing without attributions", () => {
    const { container } = render(<ModelAttributionBars data={[]} />);

    expect(container).toBeEmptyDOMElement();
  });
});
