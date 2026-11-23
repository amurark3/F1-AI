import { act, screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useServerStatus, type ServerState } from "@/app/hooks/useServerStatus";
import { SEASON_2026 } from "@/test/fixtures";
import { apiUrl, server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";

import { RacePicker } from "./RacePicker";

import type { ComponentProps } from "react";

vi.mock("@/app/hooks/useServerStatus", () => ({ useServerStatus: vi.fn() }));

const { schedule } = SEASON_2026;
const MEXICO = "R19 · Mexico City GP, Max Verstappen won · Red Bull";
const SAO_PAULO = "R20 · São Paulo GP, Lando Norris won · McLaren";
const LAS_VEGAS = "R21 · Las Vegas GP, Race day 21 Nov";

function renderPicker(props: Partial<ComponentProps<typeof RacePicker>> = {}) {
  const onSelectRound = vi.fn();
  const view = renderWithProviders(
    <RacePicker year={2026} races={schedule} selectedRound={20} onSelectRound={onSelectRound} {...props} />,
  );
  return { ...view, onSelectRound };
}

function rail(): HTMLElement {
  return screen.getByRole("listbox", { name: "2026 season rounds" });
}

/** The winners load after the calendar; until then a run round reads "Completed". */
async function winnersLoaded(): Promise<void> {
  await within(rail()).findByRole("option", { name: SAO_PAULO });
}

describe("RacePicker", () => {
  beforeEach(() => {
    vi.mocked(useServerStatus).mockReturnValue({ status: "ready" } as ServerState);
    server.use(http.get(apiUrl("/api/champions/2026"), () => HttpResponse.json(SEASON_2026.winners)));
    // jsdom lays nothing out, so it has no scrolling to do.
    Element.prototype.scrollIntoView = vi.fn();
  });

  it("names the selected round and places every round of the season on the rail", async () => {
    renderPicker();
    await winnersLoaded();

    const picker = screen.getByRole("group", { name: "2026 race picker" });
    expect(within(picker).getByText("São Paulo GP")).toBeInTheDocument();
    expect(within(picker).getByText("Autódromo José Carlos Pace (Interlagos)")).toBeInTheDocument();
    expect(within(picker).getByText("8 Nov")).toBeInTheDocument();
    expect(within(rail()).getAllByRole("option")).toHaveLength(23);
    expect(within(rail()).getByRole("option", { selected: true })).toHaveAccessibleName(SAO_PAULO);
  });

  it("names the place by its location when the calendar knows no circuit", () => {
    // `get_circuit_info` answers null for a location missing from its reference table.
    const races = schedule.map((race) => (race.round === 20 ? { ...race, circuit: null } : race));
    renderPicker({ races });

    expect(screen.getByText("São Paulo, Brazil")).toBeInTheDocument();
  });

  it("colours each run round by its winning team once the winners arrive", async () => {
    renderPicker();

    const mexico = within(rail()).getByRole("option", { name: "R19 · Mexico City GP, Completed" });
    expect(mexico.firstElementChild).not.toHaveAttribute("style");
    await waitFor(() => expect(mexico.firstElementChild).toHaveStyle({ backgroundColor: "#3671C6" }));
    expect(mexico).toHaveAccessibleName(MEXICO);
    expect(within(rail()).getByRole("option", { name: LAS_VEGAS }).firstElementChild).not.toHaveAttribute("style");
  });

  it("marks the selected round by height, never by red: a won round keeps its team's colour, any other is white", async () => {
    const { rerender, onSelectRound } = renderPicker({ selectedRound: 19 });
    const selected = () => within(rail()).getByRole("option", { selected: true }).firstElementChild!;
    await waitFor(() => expect(selected()).toHaveStyle({ backgroundColor: "#3671C6" }));
    expect(selected().className).toContain("h-[38px]");
    expect(selected().className).not.toMatch(/red/);

    rerender(<RacePicker year={2026} races={schedule} selectedRound={21} onSelectRound={onSelectRound} />);
    expect(selected().className).toContain("bg-rc-ink");
    expect(selected()).not.toHaveAttribute("style");
  });

  it("steps to the round before and after", async () => {
    const { user, onSelectRound } = renderPicker();

    await user.click(screen.getByRole("button", { name: "Previous round" }));
    expect(onSelectRound).toHaveBeenLastCalledWith(19);
    await user.click(screen.getByRole("button", { name: "Next round" }));
    expect(onSelectRound).toHaveBeenLastCalledWith(21);
  });

  it("cannot step past either end of the season", () => {
    const { rerender, onSelectRound } = renderPicker({ selectedRound: 1 });
    expect(screen.getByRole("button", { name: "Previous round" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Next round" })).toBeEnabled();

    rerender(<RacePicker year={2026} races={schedule} selectedRound={23} onSelectRound={onSelectRound} />);
    expect(screen.getByRole("button", { name: "Previous round" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Next round" })).toBeDisabled();
  });

  it("browses the rail by keyboard, previewing each round, and selects with Enter", async () => {
    const { user, onSelectRound } = renderPicker();
    await winnersLoaded();

    act(() => rail().focus());
    expect(rail()).toHaveAttribute("aria-activedescendant", within(rail()).getByRole("option", { name: SAO_PAULO }).id);
    await user.keyboard("{ArrowLeft}");
    expect(rail()).toHaveAttribute("aria-activedescendant", within(rail()).getByRole("option", { name: MEXICO }).id);
    expect(await screen.findByText("Max Verstappen won · Red Bull")).toBeInTheDocument();
    expect(onSelectRound).not.toHaveBeenCalled();

    await user.keyboard("{Enter}");
    expect(onSelectRound).toHaveBeenLastCalledWith(19);
    await user.keyboard("{End}{Enter}");
    expect(onSelectRound).toHaveBeenLastCalledWith(23);
    await user.keyboard("{Home} ");
    expect(onSelectRound).toHaveBeenLastCalledWith(1);

    act(() => rail().blur());
    expect(rail()).not.toHaveAttribute("aria-activedescendant");
  });

  it("selects a round with a click and previews one under the pointer", async () => {
    const { user, onSelectRound } = renderPicker();
    const vegas = within(rail()).getByRole("option", { name: LAS_VEGAS });

    await user.hover(vegas);
    expect(screen.getByText("Race day 21 Nov")).toBeInTheDocument();
    await user.unhover(vegas);
    expect(screen.queryByText("Race day 21 Nov")).not.toBeInTheDocument();

    await user.click(vegas);
    expect(onSelectRound).toHaveBeenLastCalledWith(21);
    await user.click(rail());
    expect(onSelectRound).toHaveBeenCalledTimes(1);
  });

  it("lists every race in a popover that the keyboard can open, walk, choose from and close", async () => {
    const { user, onSelectRound } = renderPicker();
    await winnersLoaded();
    const trigger = screen.getByRole("button", { name: "All races" });
    expect(trigger).toHaveAttribute("aria-expanded", "false");

    await user.click(trigger);
    const list = screen.getByRole("listbox", { name: "All 2026 races" });
    expect(trigger).toHaveAttribute("aria-expanded", "true");
    expect(list).toHaveFocus();
    expect(within(list).getAllByRole("option")).toHaveLength(23);
    expect(list).toHaveAttribute("aria-activedescendant", within(list).getByRole("option", { name: SAO_PAULO }).id);

    await user.keyboard("{ArrowDown}{Enter}");
    expect(onSelectRound).toHaveBeenLastCalledWith(21);
    expect(screen.queryByRole("listbox", { name: "All 2026 races" })).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();

    await user.keyboard("{Enter}");
    expect(screen.getByRole("listbox", { name: "All 2026 races" })).toHaveFocus();
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("listbox", { name: "All 2026 races" })).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();
  });

  it("chooses a race from the popover with a click, and closes on a press outside or a tab away", async () => {
    const { user, onSelectRound } = renderPicker();
    await winnersLoaded();
    const trigger = screen.getByRole("button", { name: "All races" });

    await user.click(trigger);
    await user.click(
      within(screen.getByRole("listbox", { name: "All 2026 races" })).getByRole("option", { name: MEXICO }),
    );
    expect(onSelectRound).toHaveBeenLastCalledWith(19);
    expect(screen.queryByRole("listbox", { name: "All 2026 races" })).not.toBeInTheDocument();

    await user.click(trigger);
    await user.click(screen.getByRole("listbox", { name: "All 2026 races" }));
    expect(onSelectRound).toHaveBeenCalledTimes(1);
    await user.click(document.body);
    expect(screen.queryByRole("listbox", { name: "All 2026 races" })).not.toBeInTheDocument();

    await user.click(trigger);
    await user.click(trigger);
    expect(screen.queryByRole("listbox", { name: "All 2026 races" })).not.toBeInTheDocument();

    await user.click(trigger);
    await user.tab();
    expect(screen.queryByRole("listbox", { name: "All 2026 races" })).not.toBeInTheDocument();
  });

  it("says so when the calendar is empty", () => {
    renderPicker({ races: [], selectedRound: null });

    expect(screen.getByText("Season calendar unavailable.")).toBeInTheDocument();
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
  });

  it("asks for a round when the one asked for is not on the calendar", () => {
    renderPicker({ selectedRound: 30 });

    expect(screen.getByText("Choose a round")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Previous round" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Next round" })).toBeDisabled();
    expect(within(rail()).queryByRole("option", { selected: true })).not.toBeInTheDocument();
  });
});
