import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { SiteNav } from "./SiteNav";

const nav = () => screen.getByRole("navigation", { name: "Main" });

describe("SiteNav", () => {
  it("lists the seven sections, then More, from xl up", () => {
    render(<SiteNav pathname="/race-control/telemetry" />);

    expect(nav()).toHaveClass("hidden", "xl:flex");
    expect(
      within(nav())
        .getAllByRole("link")
        .map((el) => el.textContent),
    ).toEqual(["Race Control", "Grand Prix", "Telemetry", "Standings", "Teams", "Power Units", "AI Engineer"]);
    expect(within(nav()).getByRole("button", { name: "More" })).toBeInTheDocument();
  });

  it("marks only the current section: primary tone, aria-current and the red underline", () => {
    render(<SiteNav pathname="/race-control/telemetry" />);

    const current = screen.getByRole("link", { name: "Telemetry" });
    expect(current).toHaveAttribute("aria-current", "page");
    expect(current).toHaveClass("font-mono", "uppercase", "text-rc-ink");
    expect(current.querySelector("span.bg-f1-red")).toHaveAttribute("aria-hidden", "true");

    const other = screen.getByRole("link", { name: "Grand Prix" });
    expect(other).not.toHaveAttribute("aria-current");
    expect(other).toHaveClass("text-rc-ink-3");
    expect(document.querySelectorAll("span.bg-f1-red")).toHaveLength(1);
  });

  it("lights a section from a page below it", () => {
    render(<SiteNav pathname="/race-control/drivers/lewis-hamilton" />);

    expect(screen.getByRole("link", { name: "Teams" })).toHaveAttribute("aria-current", "true");
  });

  it("lights nothing off the sections, as on the homepage", () => {
    render(<SiteNav pathname="/" />);

    for (const link of within(nav()).getAllByRole("link")) expect(link).not.toHaveAttribute("aria-current");
    expect(document.querySelector("span.bg-f1-red")).toBeNull();
  });
});
