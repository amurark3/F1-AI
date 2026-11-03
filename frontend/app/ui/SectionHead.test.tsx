import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { SectionHead } from "./SectionHead";

describe("SectionHead", () => {
  it("shows a two-digit numeral in red text, the condensed title and a hairline", () => {
    const { container } = render(<SectionHead index={1} title="Every finish" id="finishes" />);

    const numeral = screen.getByText("01");
    expect(numeral).toHaveAttribute("aria-hidden", "true");
    expect(numeral).toHaveClass("font-mono", "text-rc-red-text");

    const title = screen.getByRole("heading", { level: 2, name: "Every finish" });
    expect(title).toHaveAttribute("id", "finishes");
    expect(title).toHaveClass("font-display", "text-[34px]", "uppercase");

    expect(container.firstElementChild).toHaveClass("border-b", "border-rc-line", "items-baseline");
    expect(container.firstElementChild?.children).toHaveLength(2);
  });

  it("keeps a numeral past nine whole", () => {
    render(<SectionHead index={12} title="Penalties" />);
    expect(screen.getByText("12")).toBeInTheDocument();
  });

  it("sets a caption at the right as an eyebrow", () => {
    render(<SectionHead index={2} title="Teammates" aside="Race result by round" className="mt-14" />);

    const caption = screen.getByText("Race result by round");
    expect(caption.tagName).toBe("P");
    expect(caption).toHaveClass("font-mono", "uppercase", "text-rc-ink-3");
    expect(caption.parentElement).toHaveClass("ml-auto");
    expect(caption.closest(".mt-14")).not.toBeNull();
  });

  it("renders any other aside as given, at another heading level", () => {
    render(<SectionHead index={3} as="h3" title="Stakes" aside={<button type="button">Teams</button>} />);

    expect(screen.getByRole("heading", { level: 3 })).toHaveTextContent("Stakes");
    expect(screen.getByRole("button", { name: "Teams" }).parentElement).toHaveClass("ml-auto");
  });
});
