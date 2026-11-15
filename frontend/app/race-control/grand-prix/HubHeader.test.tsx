import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { SEASON_2026 } from "@/test/fixtures";

import { HubAlerts, RaceHeader } from "./HubHeader";

const MEXICO = SEASON_2026.schedule.find((race) => race.round === 19)!;

describe("RaceHeader", () => {
  it("names the race, its circuit, round and status, with no countdown once it is run", () => {
    render(<RaceHeader selectedRound={19} selectedRace={MEXICO} raceName="Mexico City Grand Prix" />);

    expect(screen.getByRole("heading", { level: 1, name: "Mexico City Grand Prix" })).toBeInTheDocument();
    expect(screen.getByText("Autódromo Hermanos Rodríguez")).toBeInTheDocument();
    expect(screen.getByText("Round 19")).toBeInTheDocument();
    expect(screen.getByText("Completed")).toBeInTheDocument();
    expect(screen.queryByText(/lights out in/)).not.toBeInTheDocument();
  });

  it("falls back to the location, then to placeholders, and prints a status it does not know as sent", () => {
    const { rerender } = render(
      <RaceHeader
        selectedRound={null}
        selectedRace={{ ...MEXICO, circuit: undefined, status: "red_flag" }}
        raceName="Mexico City Grand Prix"
      />,
    );
    expect(screen.getByText("Mexico City, Mexico")).toBeInTheDocument();
    expect(screen.getByText("Round -")).toBeInTheDocument();
    expect(screen.getByText("red_flag")).toBeInTheDocument();

    rerender(<RaceHeader selectedRound={null} selectedRace={null} raceName="Select A Race" />);
    expect(screen.getByText("Circuit TBC")).toBeInTheDocument();
    expect(screen.getByText("Status unknown")).toBeInTheDocument();
  });
});

describe("HubAlerts", () => {
  it("shows nothing while the calendar and the entry list are both fine", () => {
    const { container } = render(
      <HubAlerts scheduleError={false} driversError={false} onReloadSchedule={vi.fn()} onReloadDrivers={vi.fn()} />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("offers a retry for whichever failed, on its own", async () => {
    const user = userEvent.setup();
    const reloadSchedule = vi.fn();
    const reloadDrivers = vi.fn();
    render(<HubAlerts scheduleError driversError onReloadSchedule={reloadSchedule} onReloadDrivers={reloadDrivers} />);

    const [scheduleRetry, driversRetry] = screen.getAllByRole("button", { name: "Retry" });
    await user.click(driversRetry);
    expect(reloadDrivers).toHaveBeenCalledTimes(1);
    expect(reloadSchedule).not.toHaveBeenCalled();
    await user.click(scheduleRetry);
    expect(reloadSchedule).toHaveBeenCalledTimes(1);
  });
});
