import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { DeltaChip } from "./DeltaChip";

describe("DeltaChip", () => {
  it("shows places gained with a plus, in the gain colour", () => {
    const { container } = render(<DeltaChip delta={15} className="ml-2" />);

    const chip = container.firstElementChild;
    expect(chip).toHaveAttribute("data-trend", "gain");
    expect(chip).toHaveClass("ml-2", "bg-rc-gain/14", "text-rc-gain", "font-mono");
    expect(screen.getByText("+15")).toHaveAttribute("aria-hidden", "true");
    expect(screen.getByText("gained 15 places")).toHaveClass("sr-only");
  });

  it("shows places lost with a true minus, in red text", () => {
    const { container } = render(<DeltaChip delta={-1} />);

    const chip = container.firstElementChild;
    expect(chip).toHaveAttribute("data-trend", "loss");
    expect(chip).toHaveClass("bg-rc-red-text/14", "text-rc-red-text");
    expect(screen.getByText("−1")).toBeInTheDocument();
    expect(screen.getByText("lost 1 place")).toBeInTheDocument();
  });

  it.each([0, -0])("reads %d as held station, in a neutral tone", (delta) => {
    const { container } = render(<DeltaChip delta={delta} />);

    const chip = container.firstElementChild;
    expect(chip).toHaveAttribute("data-trend", "even");
    expect(chip).toHaveClass("text-rc-ink-2");
    expect(screen.getByText("0")).toBeInTheDocument();
    expect(screen.getByText("no change")).toBeInTheDocument();
  });

  it("speaks a single gained place in the singular", () => {
    render(<DeltaChip delta={1} />);
    expect(screen.getByText("gained 1 place")).toBeInTheDocument();
  });

  it("never borrows the DRS or sector colours", () => {
    for (const delta of [3, -3, 0]) {
      const { container, unmount } = render(<DeltaChip delta={delta} />);
      expect(container.firstElementChild?.className).not.toMatch(/f1-(drs|green|purple|yellow)|sector/);
      unmount();
    }
  });

  it.each([Number.NaN, Number.POSITIVE_INFINITY])("renders nothing for %d rather than a made-up zero", (delta) => {
    const { container } = render(<DeltaChip delta={delta} />);
    expect(container).toBeEmptyDOMElement();
  });
});
