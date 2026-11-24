import { render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { SiteHeader } from "./SiteHeader";

vi.mock("./RaceStatusChip", () => ({ RaceStatusChip: () => <span>Race status</span> }));
vi.mock("./WarmupLights", () => ({ WarmupLights: ({ phase }: { phase: string }) => <span>Lights: {phase}</span> }));
const hook = vi.hoisted(() => ({ useServerStatus: vi.fn() }));
vi.mock("@/app/hooks/useServerStatus", () => hook);

const up = { status: "ready", run: 1, waited: false, dismissedRun: 0, launchedRun: 0 };
beforeEach(() => hook.useServerStatus.mockReturnValue(up));

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

  it("hands the slot to the restart lights on every route and width while the backend restarts", () => {
    hook.useServerStatus.mockReturnValue({ ...up, status: "warming" });
    const { rerender } = render(<SiteHeader pathname="/" />);

    const lights = within(banner()).getByText("Lights: warming");
    expect(lights.parentElement).toHaveClass("flex");
    expect(lights.parentElement).not.toHaveClass("hidden");
    expect(within(banner()).queryByText("Race status")).toBeNull();

    rerender(<SiteHeader pathname="/race-control/telemetry" />);
    expect(within(banner()).queryByText("Race status")).toBeNull();
    expect(within(banner()).getByText("Lights: warming")).toBeInTheDocument();
  });
});
