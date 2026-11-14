import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { SiteHeader } from "./SiteHeader";

vi.mock("./RaceStatusChip", () => ({ RaceStatusChip: () => <span>Race status</span> }));

const banner = () => screen.getByRole("banner");

describe("SiteHeader", () => {
  it("is the sticky top bar: the lockup home, the links, MENU and the red streak", () => {
    render(<SiteHeader pathname="/race-control/telemetry" />);

    expect(banner()).toHaveClass("sticky", "top-0", "border-rc-line", "bg-background/94");
    const home = within(banner()).getByRole("link", { name: "F1 AI home" });
    expect(home).toHaveAttribute("href", "/");
    expect(within(home).getByRole("img", { name: "F1 AI" })).toBeInTheDocument();
    expect(within(banner()).getByRole("navigation", { name: "Main" })).toBeInTheDocument();
    expect(within(banner()).getByRole("button", { name: "Menu" })).toBeInTheDocument();
    expect(banner().lastElementChild).toHaveClass("h-0.5", "bg-f1-red");
    expect(banner().lastElementChild).toHaveAttribute("aria-hidden", "true");
  });

  it("holds the race status in its slot on data routes, from sm up", () => {
    render(<SiteHeader pathname="/race-control/telemetry" />);

    const chip = within(banner()).getByText("Race status");
    expect(chip.parentElement).toHaveClass("hidden", "sm:flex");
  });

  it("leaves the slot empty on the static homepage", () => {
    render(<SiteHeader pathname="/" />);

    expect(within(banner()).queryByText("Race status")).toBeNull();
  });
});
