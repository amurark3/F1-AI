import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { PanelHeading } from "./PanelHeading";

describe("PanelHeading", () => {
  it("heads a chart card with an eyebrow, the finding as an h3 and a reading note", () => {
    render(
      <PanelHeading
        eyebrow="Degradation"
        title="Lap times rose about 0.06 s per lap of tyre age"
        sub="Fuel-corrected · top five finishers"
      />,
    );

    const title = screen.getByRole("heading", { level: 3, name: "Lap times rose about 0.06 s per lap of tyre age" });
    expect(title).toHaveClass("font-display", "text-[26px]", "uppercase", "text-balance");
    expect(screen.getByText("Degradation")).toHaveClass("font-mono", "text-rc-ink-3");
    expect(screen.getByText("Fuel-corrected · top five finishers")).toHaveClass("text-xs", "text-rc-ink-3");
  });

  it("puts a control at the right and takes another heading level", () => {
    const { container } = render(
      <PanelHeading
        as="h2"
        title="Four drivers, sixteen points"
        aside={<button type="button">Drivers</button>}
        className="mt-4"
      />,
    );

    expect(screen.getByRole("heading", { level: 2 })).toHaveTextContent("Four drivers, sixteen points");
    expect(screen.getByRole("button", { name: "Drivers" }).parentElement).toHaveClass("shrink-0");
    expect(container.firstElementChild).toHaveClass("mt-4", "justify-between");
  });

  it("renders the title alone when given nothing else", () => {
    const { container } = render(<PanelHeading title="Schedule" />);

    expect(container.firstElementChild?.children).toHaveLength(1);
    expect(container.querySelectorAll("p")).toHaveLength(0);
  });
});
