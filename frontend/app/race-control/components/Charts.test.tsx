import { render, screen } from "@testing-library/react";
import { cloneElement, isValidElement, type ComponentProps, type ReactElement, type ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

import { f1, rc } from "@/app/ui/tokens";

import { ModelAttributionBars } from "./Charts";

import type * as Recharts from "recharts";

// jsdom has no layout, so the responsive wrapper would measure 0 × 0 and draw
// nothing: hand the chart a fixed size. Bars grow in from zero over animation
// frames jsdom never paints, so they are drawn at rest.
// The tooltip only draws under a pointer, which jsdom cannot hover: hand its content
// the props recharts would pass.
const tooltipProps = vi.hoisted(() => {
  const initial: { active?: boolean; payload?: unknown[] } = { active: false };
  return { current: initial };
});

vi.mock("recharts", async (importOriginal) => {
  const recharts = await importOriginal<typeof Recharts>();
  const { Bar } = recharts;
  return {
    ...recharts,
    Bar: (props: ComponentProps<typeof Bar>) => <Bar {...props} isAnimationActive={false} />,
    Tooltip: ({ content }: { content: ReactElement }) => cloneElement(content, tooltipProps.current),
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

describe("attribution tooltip", () => {
  const hover = (contribution: number | undefined) => {
    tooltipProps.current =
      contribution === undefined
        ? { active: true, payload: [] }
        : { active: true, payload: [{ payload: { label: "Grid position", contribution } }] };
    render(<ModelAttributionBars data={[{ label: "Grid position", contribution: contribution ?? 0 }]} />);
  };

  it("says how many places a factor gains, in the gain token", () => {
    hover(-1.8);

    expect(screen.getByText("improves projection by 1.80 places")).toHaveStyle({ color: rc.gain });
  });

  it("says how many places a factor loses, in red text", () => {
    hover(0.4);

    expect(screen.getByText("worsens projection by 0.40 places")).toHaveStyle({ color: rc.redText });
  });

  it("stays hidden with no pointer or no payload", () => {
    tooltipProps.current = { active: false };
    const idle = render(<ModelAttributionBars data={[{ label: "Grid position", contribution: 1 }]} />);
    expect(idle.container.textContent).not.toContain("projection");
    idle.unmount();

    hover(undefined);
    expect(screen.queryByText(/projection by/)).not.toBeInTheDocument();
  });
});
