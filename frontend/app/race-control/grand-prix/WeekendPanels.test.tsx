import { act, screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { renderToString } from "react-dom/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useServerStatus, type ServerState } from "@/app/hooks/useServerStatus";
import { DIRECTORY_2026, MEXICO_CITY_2026, RACE_RESULTS_2026, SAO_PAULO_2026, SEASON_2026 } from "@/test/fixtures";
import { apiUrl, server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";

import { WeekendPanel, WeekendTop } from "./WeekendPanels";

import type { RaceEvent } from "./predictionModel";

/** The Weekend tab as the hub draws it: the hero and facts above the tabs, the panels below. */
function Weekend({ race }: { race: RaceEvent }) {
  return (
    <>
      <WeekendTop year={2026} race={race} totalRounds={SEASON_2026.schedule.length} />
      <WeekendPanel year={2026} selectedRace={race} />
    </>
  );
}

vi.mock("@/app/hooks/useServerStatus", () => ({ useServerStatus: vi.fn() }));

const MEXICO = SEASON_2026.schedule.find((race) => race.round === 19)!;
const LAS_VEGAS = SEASON_2026.schedule.find((race) => race.round === 21)!;
const SHELL = { race: MEXICO, stakes: SAO_PAULO_2026.stakes };

function backend(overrides: { circuit?: unknown; results?: unknown; shell?: unknown; glance?: unknown } = {}): void {
  const json = (body: unknown) => HttpResponse.json(body as Record<string, unknown>);
  server.use(
    http.get(apiUrl("/api/profiles/:year/directory"), () => json(DIRECTORY_2026)),
    http.get(apiUrl("/api/race-control/circuit/:year/:round"), () =>
      json(overrides.circuit ?? MEXICO_CITY_2026.circuit),
    ),
    http.get(apiUrl("/api/race-control/results/:year/:round"), () =>
      json(overrides.results ?? RACE_RESULTS_2026.mexicoCity),
    ),
    http.get(apiUrl("/api/race-control/overview/:year/shell"), () => json(overrides.shell ?? SHELL)),
    http.get(apiUrl("/api/race-control/glance/:year/:round"), () => json(overrides.glance ?? MEXICO_CITY_2026.glance)),
  );
}

describe("WeekendPanel", () => {
  beforeEach(() => {
    vi.mocked(useServerStatus).mockReturnValue({ status: "ready" } as ServerState);
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("after the race replaces the countdown with the winner and a link to Results", async () => {
    backend();
    renderWithProviders(<Weekend race={MEXICO} />);

    expect(screen.getByRole("heading", { level: 1, name: "Mexico City Grand\u00a0Prix" })).toBeInTheDocument();
    expect(screen.getByText(`Round 19 / ${SEASON_2026.schedule.length} · Mexico`)).toBeInTheDocument();
    expect(screen.getByText("Completed")).toBeInTheDocument();
    const winner = (await screen.findByText("Winner")).parentElement!;
    expect(await within(winner).findByText("Max Verstappen")).toBeInTheDocument();
    expect(within(winner).getByText("Red Bull")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Final classification →" })).toHaveAttribute(
      "href",
      "/race-control/grand-prix?round=19&tab=results",
    );
    expect(screen.queryByRole("timer")).not.toBeInTheDocument();
    // The winner is not repeated in the facts: Circuit history lists past winners.
    expect(screen.queryByText(/winner$/)).not.toBeInTheDocument();
  });

  it("shows the circuit's map and its four figures, the schedule, the history and the stakes", async () => {
    backend();
    renderWithProviders(<Weekend race={MEXICO} />);

    expect(await screen.findByRole("img", { name: /layout/ })).toBeInTheDocument();
    expect(screen.getByText(/Layout · /)).toBeInTheDocument();
    for (const fact of ["4.304", "305.4", "Clockwise"]) {
      expect(screen.getByText(fact)).toBeInTheDocument();
    }
    const schedule = screen.getByText("Schedule").closest("section")!;
    expect(within(schedule).getAllByRole("listitem")).toHaveLength(5);
    // Date and time are separate boxes, so the row's gap sits between them ("Oct 30, 2026  11:30 AM", not "202611:30").
    const first = within(within(schedule).getAllByRole("listitem")[0]);
    expect(first.getByText(/^[A-Z][a-z]{2} \d{1,2}, \d{4}$/)).toBeInTheDocument();
    expect(first.getByText(/^\d{1,2}:\d{2}/)).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: "History" })).toBeInTheDocument();
    expect(await screen.findByText("What's at stake")).toBeInTheDocument();
    expect(await screen.findByText(/2025 pole/)).toBeInTheDocument();
  });

  it("leaves the stakes out on a round the shell is not about", async () => {
    backend({ shell: { race: LAS_VEGAS, stakes: SAO_PAULO_2026.stakes } });
    renderWithProviders(<Weekend race={MEXICO} />);

    await screen.findByText("Winner");
    await screen.findByText(/2025 pole/);
    expect(screen.queryByText("What's at stake")).not.toBeInTheDocument();
  });

  it("leaves the stakes out when the shell has none", async () => {
    backend({ shell: { race: MEXICO } });
    renderWithProviders(<Weekend race={MEXICO} />);

    await screen.findByText("Winner");
    expect(screen.queryByText("What's at stake")).not.toBeInTheDocument();
  });

  it("says when the classification is not published, and tags a provisional winner", async () => {
    backend({ results: { ...RACE_RESULTS_2026.mexicoCity, race: null } });
    const { unmount } = renderWithProviders(<Weekend race={MEXICO} />);
    expect(await screen.findByText("The classification is not published yet.")).toBeInTheDocument();
    unmount();

    const race = RACE_RESULTS_2026.mexicoCity.race!;
    backend({ results: { ...RACE_RESULTS_2026.mexicoCity, race: { ...race, final: false } } });
    renderWithProviders(<Weekend race={MEXICO} />);
    expect(await screen.findByText("Winner · provisional")).toBeInTheDocument();
  });

  it("counts down to the next session before the weekend, and names it", async () => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date("2026-11-19T12:00:00Z"));
    backend({ circuit: { ...MEXICO_CITY_2026.circuit, map: null } });
    renderWithProviders(<Weekend race={LAS_VEGAS} />);

    expect(await screen.findByRole("timer", { name: "Time to Practice 1" })).toBeInTheDocument();
    expect(screen.getByRole("timer", { name: "Time to Practice 1" })).toBeInTheDocument();
    expect(await screen.findByText("Circuit map unavailable")).toBeInTheDocument();
    expect(screen.queryByText("Winner")).not.toBeInTheDocument();
  });

  it("says Live now while a session is on track, and Weekend complete once all are run", async () => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date("2026-11-20T00:45:00Z"));
    backend();
    const first = renderWithProviders(<Weekend race={LAS_VEGAS} />);
    expect(await screen.findByText("Live now · Practice 1")).toBeInTheDocument();
    first.unmount();

    vi.setSystemTime(new Date("2026-11-30T00:00:00Z"));
    renderWithProviders(<Weekend race={LAS_VEGAS} />);
    expect(await screen.findByText("Weekend complete")).toBeInTheDocument();
  });

  it("names a weekend with no published times, and a circuit the backend could not read", async () => {
    backend();
    server.use(http.get(apiUrl("/api/race-control/circuit/:year/:round"), () => HttpResponse.json({ error: "down" })));
    renderWithProviders(<Weekend race={{ ...LAS_VEGAS, sessions: undefined }} />);

    expect(await screen.findByText("Session times have not been returned for this event.")).toBeInTheDocument();
    await waitFor(() => expect(screen.getAllByText(/unavailable/).length).toBeGreaterThan(0));
    expect(screen.getAllByText("-").length).toBeGreaterThan(0);
  });

  it("names the circuit from the schedule when f1db has no record, then from the location", async () => {
    backend({ circuit: { ...MEXICO_CITY_2026.circuit, record: null } });
    const { unmount } = renderWithProviders(<Weekend race={MEXICO} />);
    expect(await screen.findByText("Autódromo Hermanos Rodríguez · Mexico City")).toBeInTheDocument();
    unmount();

    renderWithProviders(<Weekend race={{ ...MEXICO, circuit: undefined }} />);
    // The city alone, never "Mexico City, Mexico · Mexico City".
    expect(await screen.findByText("Mexico City")).toBeInTheDocument();
  });

  it("heads an upcoming round in blue, and copes with a city alone and a status it does not know", () => {
    backend();
    const { unmount } = renderWithProviders(<Weekend race={LAS_VEGAS} />);
    expect(screen.getByText("Upcoming")).toBeInTheDocument();
    expect(screen.getByText("Upcoming").className).toContain("text-rc-blue");
    unmount();

    renderWithProviders(<Weekend race={{ ...LAS_VEGAS, location: "Las Vegas", status: "postponed" }} />);
    expect(screen.getByText(`Round 21 / ${SEASON_2026.schedule.length}`)).toBeInTheDocument();
    expect(screen.getByText("postponed")).toBeInTheDocument();
  });

  it("renders a placeholder countdown on the server, where there is no clock", () => {
    const html = renderToString(<Weekend race={LAS_VEGAS} />);
    expect(html).toContain("Next · ");
    expect(html).toContain("session");
    expect(html).toContain("--");
  });

  it("asks for a race when none is selected", () => {
    renderWithProviders(<WeekendPanel year={2026} selectedRace={null} />);
    expect(screen.getByText("Pick a race to see its weekend.")).toBeInTheDocument();
  });

  it("keeps ticking: the schedule's states follow the clock", async () => {
    vi.useFakeTimers({ toFake: ["Date", "setInterval", "clearInterval"] });
    vi.setSystemTime(new Date("2026-11-19T12:00:00Z"));
    backend();
    renderWithProviders(<Weekend race={LAS_VEGAS} />);
    expect(await screen.findByText("Next")).toBeInTheDocument();

    await act(async () => {
      vi.setSystemTime(new Date("2026-11-20T00:40:00Z"));
      await vi.advanceTimersByTimeAsync(1000);
    });
    expect(screen.getAllByText("Live").length).toBeGreaterThan(0);
  });
});
