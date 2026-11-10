import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { RetryButton, Section, StaleMark } from "./Section";

import type { SectionState, SectionStatus } from "./sectionState";

function state(status: SectionStatus, reason: string | null = null, refreshing = false): SectionState {
  return { status, reason, refreshing, retry: vi.fn() };
}

function renderSection(section: SectionState, className?: string) {
  return render(
    <Section state={section} label="Weather feed" skeletonClassName="h-[440px]" className={className}>
      <p>Race 21% rain</p>
    </Section>,
  );
}

describe("Section", () => {
  it("holds a skeleton of the given size while pending, marked busy", () => {
    const { container } = renderSection(state("pending"), "h-full");

    const frame = container.firstElementChild;
    expect(frame).toHaveAttribute("aria-busy", "true");
    expect(frame).toHaveClass("flex", "flex-col", "h-full");
    expect(container.querySelector(".h-\\[440px\\]")).toBeInTheDocument();
    expect(screen.queryByText("Race 21% rain")).not.toBeInTheDocument();
    expect(screen.getByRole("status")).toBeEmptyDOMElement();
  });

  it("shows its content when ready, with nothing else", () => {
    const { container } = renderSection(state("ready"));

    expect(container.firstElementChild).toHaveAttribute("aria-busy", "false");
    expect(screen.getByText("Race 21% rain")).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    expect(screen.queryByText(/unavailable/i)).not.toBeInTheDocument();
    expect(screen.getByRole("status")).toBeEmptyDOMElement();
  });

  it("keeps its content after a failed refresh, with a quiet mark and a retry", async () => {
    const stale = state("stale", "Request failed: 500 Internal Server Error");
    renderSection(stale);

    expect(screen.getByText("Race 21% rain")).toBeInTheDocument();
    expect(screen.getByText("Couldn't refresh")).toBeInTheDocument();
    expect(screen.queryByText(/unavailable/i)).not.toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent(
      "Weather feed couldn't refresh. Showing the last data received. Request failed: 500 Internal Server Error",
    );

    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(stale.retry).toHaveBeenCalledTimes(1);
  });

  it("says why it has no data and offers a retry when it failed", async () => {
    const failed = state("failed", "Could not reach the server.");
    renderSection(failed);

    expect(screen.queryByText("Race 21% rain")).not.toBeInTheDocument();
    expect(screen.getByText("Weather feed unavailable")).toBeInTheDocument();
    expect(screen.getByText("Could not reach the server.")).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("Weather feed unavailable. Could not reach the server.");

    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(failed.retry).toHaveBeenCalledTimes(1);
  });

  it("announces a failure that came without a reason, and falls back to a default skeleton", () => {
    const { rerender, container } = render(
      <Section state={state("failed")} label="Weather feed">
        <p>Race 21% rain</p>
      </Section>,
    );
    expect(screen.getByRole("status")).toHaveTextContent(/^Weather feed unavailable\.$/);

    rerender(
      <Section state={state("pending")} label="Weather feed">
        <p>Race 21% rain</p>
      </Section>,
    );
    expect(container.querySelector(".h-32")).toBeInTheDocument();
  });

  it("shows a retry in flight", () => {
    renderSection(state("failed", "Could not reach the server.", true));

    expect(screen.getByRole("button", { name: "Retrying…" })).toBeInTheDocument();
  });
});

describe("StaleMark", () => {
  it("names the failed refresh and takes the caller's placement", () => {
    const { container } = render(<StaleMark state={state("stale", "Could not reach the server.")} className="mt-2" />);

    expect(container.firstElementChild).toHaveClass("mt-2");
    expect(screen.getByText("Couldn't refresh")).toHaveAttribute("title", "Could not reach the server.");
  });

  it("leaves the reason off when there is none", () => {
    render(<StaleMark state={state("stale")} />);

    expect(screen.getByText("Couldn't refresh")).not.toHaveAttribute("title");
  });
});

describe("RetryButton", () => {
  it("is a real button, quiet by default and framed on request", () => {
    const { rerender } = render(<RetryButton state={state("failed")} />);

    const button = screen.getByRole("button", { name: "Retry" });
    expect(button).toHaveAttribute("type", "button");
    expect(button).not.toHaveClass("border");

    rerender(<RetryButton state={state("failed")} framed className="mt-3" />);
    expect(screen.getByRole("button", { name: "Retry" })).toHaveClass("border", "mt-3");
  });
});
