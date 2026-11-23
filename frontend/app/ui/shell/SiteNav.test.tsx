import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { SiteNav } from "./SiteNav";

const nav = () => screen.getByRole("navigation", { name: "Main" });
const trigger = (name: string) => within(nav()).getByRole("button", { name });

describe("SiteNav", () => {
  it("shows direct links and all three disclosures from lg up", () => {
    render(<SiteNav pathname="/race-control/telemetry" />);

    expect(nav()).toHaveClass("hidden", "lg:flex");
    expect(
      within(nav())
        .getAllByRole("link")
        .map((el) => el.textContent),
    ).toEqual(["Race Control", "AI Engineer"]);
    expect(
      within(nav())
        .getAllByRole("button")
        .map((el) => el.textContent),
    ).toEqual(["Races", "Season", "Reference"]);
  });

  it("marks the current group and uses aria-current on its link", async () => {
    const user = userEvent.setup();
    render(<SiteNav pathname="/race-control/telemetry" />);

    const races = trigger("Races");
    expect(races).toHaveClass("font-mono", "uppercase", "text-rc-ink");
    expect(races.querySelector("span.bg-f1-red")).toHaveAttribute("aria-hidden", "true");
    expect(trigger("Season")).toHaveClass("text-rc-ink-3");
    expect(
      within(nav())
        .getAllByRole("button")
        .filter((button) => button.querySelector("span.bg-f1-red")),
    ).toEqual([races]);

    await user.click(races);
    expect(within(nav()).getByRole("link", { name: /^Telemetry/ })).toHaveAttribute("aria-current", "page");
    expect(within(nav()).getByRole("link", { name: /^Grand Prix/ })).not.toHaveAttribute("aria-current");
  });

  it("opens one group at a time, resets on navigation, and marks an owned route", async () => {
    const user = userEvent.setup();
    const { rerender } = render(<SiteNav pathname="/race-control/drivers/lewis-hamilton" />);

    await user.click(trigger("Season"));
    expect(within(nav()).getByRole("link", { name: /^Teams & drivers/ })).toHaveAttribute("aria-current", "true");
    await user.click(trigger("Reference"));
    expect(trigger("Season")).toHaveAttribute("aria-expanded", "false");
    expect(trigger("Reference")).toHaveAttribute("aria-expanded", "true");

    rerender(<SiteNav pathname="/race-control/engineer" />);
    expect(trigger("Reference")).toHaveAttribute("aria-expanded", "false");
    expect(within(nav()).getByRole("link", { name: "AI Engineer" })).toHaveAttribute("aria-current", "page");
  });

  it("lights nothing off the sections, as on the homepage", () => {
    render(<SiteNav pathname="/" />);

    for (const link of within(nav()).getAllByRole("link")) expect(link).not.toHaveAttribute("aria-current");
    expect(document.querySelector("span.bg-f1-red")).toBeNull();
  });
});
