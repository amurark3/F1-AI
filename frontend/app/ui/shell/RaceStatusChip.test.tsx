import { screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useServerStatus, type ServerState } from "@/app/hooks/useServerStatus";
import { SAO_PAULO_2026 } from "@/test/fixtures";
import { apiUrl, server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";

import { RaceStatusChip } from "./RaceStatusChip";

vi.mock("@/app/hooks/useServerStatus", () => ({ useServerStatus: vi.fn() }));

const SHELL_URL = apiUrl("/api/race-control/overview/2026/shell");

/** Pins the wall clock; timers stay real, so the shared clock still ticks and requests still land. */
function at(iso: string): void {
  vi.useFakeTimers({ toFake: ["Date"], now: new Date(iso) });
}

function serveShell(body: object): void {
  server.use(http.get(SHELL_URL, () => HttpResponse.json(body)));
}

const chip = (name: RegExp) => screen.findByRole("button", { name });

beforeEach(() => {
  vi.mocked(useServerStatus).mockReturnValue({ status: "ready" } as ServerState);
});

afterEach(() => {
  vi.useRealTimers();
});

describe("RaceStatusChip", () => {
  it("shows the round and pre-race, with the next session's countdown on hover", async () => {
    at("2026-11-03T13:15:30Z");
    serveShell({ year: 2026, race: SAO_PAULO_2026.race });
    const { user } = renderWithProviders(<RaceStatusChip />);

    const trigger = await chip(/^R20 · Pre-race$/);
    expect(trigger).toHaveClass("font-mono", "uppercase", "text-rc-ink-2");
    expect(trigger.querySelector("[aria-hidden]")).toHaveClass("bg-rc-blue");

    await user.hover(trigger);
    const tip = screen.getByRole("tooltip");
    expect(tip).toHaveTextContent(/^São Paulo Grand PrixPractice 1 in 3d 02h 1\dm$/);
    expect(trigger).toHaveAccessibleDescription(/São Paulo Grand Prix/);
  });

  it("names the live session, its dot pulsing only for readers who allow motion", async () => {
    at("2026-11-07T18:20:00Z");
    serveShell({ year: 2026, race: SAO_PAULO_2026.race });
    renderWithProviders(<RaceStatusChip />);

    const trigger = await chip(/^R20 · Qualifying live$/);
    expect(trigger.querySelector("[aria-hidden]")).toHaveClass("bg-rc-red-text", "motion-safe:animate-pulse");
    expect(screen.getByRole("tooltip", { hidden: true })).toHaveTextContent("Qualifying is on track");
  });

  it("reads post-race once the weekend has run, and drops the second line when there is none", async () => {
    at("2026-11-09T12:00:00Z");
    serveShell({ year: 2026, race: SAO_PAULO_2026.race });
    const { unmount } = renderWithProviders(<RaceStatusChip />);

    const trigger = await chip(/^R20 · Post-race$/);
    expect(trigger.querySelector("[aria-hidden]")).toHaveClass("bg-rc-ink-3");
    unmount();

    serveShell({ year: 2026, race: { ...SAO_PAULO_2026.race, sessions: {} } });
    renderWithProviders(<RaceStatusChip />);
    await chip(/^R20 · Pre-race$/);
    expect(screen.getByRole("tooltip", { hidden: true }).children).toHaveLength(1);
  });

  it("asks for the calendar year's season", async () => {
    at("2027-03-01T00:00:00Z");
    server.use(
      http.get(apiUrl("/api/race-control/overview/2027/shell"), () =>
        HttpResponse.json({ year: 2027, race: { ...SAO_PAULO_2026.race, round: 1, name: "Australian Grand Prix" } }),
      ),
    );
    renderWithProviders(<RaceStatusChip />);

    expect(await chip(/^R1 · Post-race$/)).toBeInTheDocument();
  });

  it("shows nothing while the segment loads, when it fails, or when there is no race", async () => {
    at("2026-11-03T00:00:00Z");
    let answered = false;
    server.use(
      http.get(SHELL_URL, () => {
        answered = true;
        return new HttpResponse(null, { status: 500 });
      }),
    );
    const { container, unmount } = renderWithProviders(<RaceStatusChip />);
    expect(container).toBeEmptyDOMElement();
    await waitFor(() => expect(answered).toBe(true));
    expect(container).toBeEmptyDOMElement();
    unmount();

    serveShell({ year: 2026, race: null });
    const quiet = renderWithProviders(<RaceStatusChip />);
    await waitFor(() => expect(answered).toBe(true));
    expect(quiet.container).toBeEmptyDOMElement();
  });
});
