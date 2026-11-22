import { screen, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useServerStatus, type ServerState } from "@/app/hooks/useServerStatus";
import { OVERVIEW_SEGMENTS_2026 } from "@/test/fixtures";
import { apiUrl, server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";

import { StarterPrompts } from "./StarterPrompts";

vi.mock("@/app/hooks/useServerStatus", () => ({ useServerStatus: vi.fn() }));

const SHELL_URL = apiUrl("/api/race-control/overview/2026/shell");

describe("StarterPrompts", () => {
  beforeEach(() => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date(2026, 10, 22, 12));
    vi.mocked(useServerStatus).mockReturnValue({ status: "ready" } as ServerState);
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("shows the four questions computed from the shell segment, and the data they came from", async () => {
    server.use(http.get(SHELL_URL, () => HttpResponse.json(OVERVIEW_SEGMENTS_2026.shell)));
    renderWithProviders(<StarterPrompts isLoading={false} onAsk={vi.fn()} />);

    expect(
      await screen.findByRole("button", { name: /Who does the model favour for the São Paulo Grand Prix/ }),
    ).toBeVisible();
    const buttons = screen.getAllByRole("button");
    expect(buttons.map((button) => button.textContent)).toEqual([
      "Drivers' championshipWho can still finish second in the drivers' championship?",
      "Constructors' championshipCan Ferrari still beat Mercedes to the constructors' title?",
      "Round 20 · UpcomingWho does the model favour for the São Paulo Grand Prix?",
      "RulesWhen does a parc fermé change mean a pit-lane start?",
    ]);
    const chips = within(screen.getByRole("list", { name: "Sources" })).getAllByRole("listitem");
    expect(chips.map((chip) => chip.textContent)).toEqual([
      "f1db v2026.19.0 · standings after R19",
      "calendar · round 20",
    ]);
    expect(screen.getByText("Engineer")).toBeInTheDocument();
    expect(screen.getByText("Start with")).toBeInTheDocument();
  });

  it("asks a question at once when its button is pressed", async () => {
    server.use(http.get(SHELL_URL, () => HttpResponse.json(OVERVIEW_SEGMENTS_2026.shell)));
    const onAsk = vi.fn();
    const { user } = renderWithProviders(<StarterPrompts isLoading={false} onAsk={onAsk} />);

    await user.click(await screen.findByRole("button", { name: /Can Ferrari still beat Mercedes/ }));

    expect(onAsk).toHaveBeenCalledWith("Can Ferrari still beat Mercedes to the constructors' title?");
  });

  it("leaves only the rules question, and no chips, when the shell segment fails", async () => {
    server.use(http.get(SHELL_URL, () => HttpResponse.json({ detail: "boom" }, { status: 500 })));
    renderWithProviders(<StarterPrompts isLoading={false} onAsk={vi.fn()} />);

    expect(await screen.findByRole("button", { name: /parc fermé/ })).toBeVisible();
    expect(screen.getAllByRole("button")).toHaveLength(1);
    expect(screen.queryByRole("list", { name: "Sources" })).toBeNull();
    expect(screen.queryByText(/unavailable/i)).toBeNull();
  });

  it("disables the questions while an answer is on its way", async () => {
    server.use(http.get(SHELL_URL, () => HttpResponse.json(OVERVIEW_SEGMENTS_2026.shell)));
    renderWithProviders(<StarterPrompts isLoading onAsk={vi.fn()} />);

    const buttons = await screen.findAllByRole("button");
    expect(buttons.every((button) => button.hasAttribute("disabled"))).toBe(true);
  });
});
