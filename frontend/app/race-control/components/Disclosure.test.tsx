import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { Disclosure } from "./Disclosure";

describe("Disclosure", () => {
  it("starts closed with its title and hint in the summary row", () => {
    const { container } = render(
      <Disclosure title="Penalty points" hint="3 drivers" className="mt-4">
        <p>Body</p>
      </Disclosure>,
    );

    const details = container.querySelector("details");
    expect(details).not.toHaveAttribute("open");
    expect(details).toHaveClass("mt-4");
    expect(screen.getByText("Penalty points").closest("summary")).toBeInTheDocument();
    expect(screen.getByText("3 drivers")).toHaveClass("text-xs");
  });

  it("opens by default when asked and leaves the hint out when there is none", () => {
    const { container } = render(
      <Disclosure title="Rules" defaultOpen>
        <p>Body</p>
      </Disclosure>,
    );

    expect(container.querySelector("details")).toHaveAttribute("open");
    expect(container.querySelector("summary")?.children).toHaveLength(1);
  });

  it("reports each open and close", () => {
    const onOpenChange = vi.fn<(open: boolean) => void>();
    const { container } = render(
      <Disclosure title="Rules" onOpenChange={onOpenChange}>
        <p>Body</p>
      </Disclosure>,
    );
    const details = container.querySelector("details");
    if (!details) throw new Error("no details element");

    details.open = true;
    fireEvent(details, new Event("toggle"));
    details.open = false;
    fireEvent(details, new Event("toggle"));

    expect(onOpenChange.mock.calls).toEqual([[true], [false]]);
  });

  it("toggles quietly without a listener", () => {
    const { container } = render(
      <Disclosure title="Rules">
        <p>Body</p>
      </Disclosure>,
    );
    const details = container.querySelector("details");
    if (!details) throw new Error("no details element");

    details.open = true;
    expect(() => fireEvent(details, new Event("toggle"))).not.toThrow();
  });

  it("draws the shared focus ring inside the summary, which sits flush with the clipped edge", () => {
    const { container } = render(
      <Disclosure title="Rules">
        <p>Body</p>
      </Disclosure>,
    );

    const summary = container.querySelector("summary");
    expect(summary).toHaveClass("focus-visible:-outline-offset-2");
    expect(summary?.className).not.toMatch(/ring|00FF78/i);
  });
});
