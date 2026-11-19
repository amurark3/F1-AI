import { act, screen, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useServerStatus, type ServerState } from "@/app/hooks/useServerStatus";
import { DIRECTORY_2026, SEASON_2026 } from "@/test/fixtures";
import { DEBRIEF_R19 } from "@/test/fixtures/debrief";
import { apiUrl, server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";

import { Debriefs } from "./Debriefs";

import type { DebriefSeeds } from "./useDebriefSections";

const nav = vi.hoisted(() => ({ search: "round=19", replace: vi.fn() }));

vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(nav.search),
  useRouter: () => ({ replace: nav.replace }),
  usePathname: () => "/race-control/debriefs",
}));
vi.mock("@/app/hooks/useServerStatus", () => ({ useServerStatus: vi.fn() }));

const SCHEDULE_URL = apiUrl("/api/schedule/2026");
const PART = (part: string) => apiUrl(`/api/race-control/debrief/2026/:round${part}`);

function seeds(changes: Partial<DebriefSeeds> = {}): DebriefSeeds {
  return {
    schedule: Promise.resolve(SEASON_2026.schedule),
    summary: Promise.resolve({ round: 20, data: { ...DEBRIEF_R19.summary, round: 20 } }),
    ...changes,
  };
}

async function renderPage(changes: Partial<DebriefSeeds> = {}) {
  let rendered: ReturnType<typeof renderWithProviders> | undefined;
  await act(() => {
    rendered = renderWithProviders(<Debriefs year={2026} seeds={seeds(changes)} />);
    return Promise.resolve();
  });
  return rendered!;
}

function serveRace(asked: string[] = []) {
  server.use(
    http.get(apiUrl("/api/profiles/:year/directory"), () => HttpResponse.json(DIRECTORY_2026)),
    http.get(SCHEDULE_URL, () => HttpResponse.json(SEASON_2026.schedule)),
    http.get(apiUrl("/api/champions/:year"), () => HttpResponse.json(SEASON_2026.winners)),
    http.get(PART(""), ({ params }) => {
      asked.push(String(params.round));
      return HttpResponse.json({ ...DEBRIEF_R19.summary, round: Number(params.round) });
    }),
    http.get(PART("/laps"), () => HttpResponse.json(DEBRIEF_R19.laps)),
    http.get(PART("/penalties"), () => HttpResponse.json(DEBRIEF_R19.penalties)),
    http.get(PART("/overtakes"), () => HttpResponse.json(DEBRIEF_R19.overtakes)),
  );
}

describe("the Debriefs page", () => {
  beforeEach(() => {
    nav.search = "round=19";
    nav.replace.mockClear();
    vi.mocked(useServerStatus).mockReturnValue({ status: "ready" } as ServerState);
    serveRace();
  });

  it("renders Mexico City's debrief: hero, banner, KPIs and both numbered sections", async () => {
    const { container } = await renderPage();

    expect(
      await screen.findByRole("heading", {
        level: 1,
        name: "Verstappen wins the Mexican Grand Prix; Antonelli is champion",
      }),
    ).toBeInTheDocument();
    expect(await screen.findByText(/380 points, 119 clear of Max Verstappen/)).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: "How the race unfolded" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Who moved, who paid" })).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: "Verstappen led from lap 44 to the flag" })).toBeInTheDocument();
    expect(container.querySelectorAll(".contents > .flex-1")).toHaveLength(71);
    expect(await screen.findByRole("heading", { name: "7 drivers penalised" })).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: "Hadjar made the most position changes" })).toBeInTheDocument();
    expect(await screen.findByText("273")).toBeInTheDocument();
    expect(screen.getByText(/Classification: f1db v2026.20.0/)).toBeInTheDocument();
  });

  it("lists completed rounds only and writes the picked round to the URL", async () => {
    nav.search = "round=20";
    const { user } = await renderPage();

    expect(await screen.findByRole("button", { name: "Next round" })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "Previous round" }));
    expect(nav.replace).toHaveBeenCalledWith("/race-control/debriefs?round=19", { scroll: false });
  });

  it("opens the latest completed round for a round off the calendar or still to run, from the server's seed", async () => {
    const asked: string[] = [];
    serveRace(asked);
    for (const search of ["round=99", "round=21", "round=nonsense", ""]) {
      nav.search = search;
      const { unmount } = await renderPage();
      expect(await screen.findByText("Race debrief · Round 20 · Mexican Grand Prix")).toBeInTheDocument();
      unmount();
    }

    expect(new Set(asked)).toEqual(new Set(["20"]));
  });

  it("fetches a round the seed does not hold", async () => {
    const asked: string[] = [];
    serveRace(asked);
    await renderPage();

    expect(await screen.findByText("Race debrief · Round 19 · Mexican Grand Prix")).toBeInTheDocument();
    expect(asked).toEqual(["19"]);
  });

  it("keeps the other sections when one fails, and recovers on retry", async () => {
    server.use(
      http.get(PART("/laps"), () => new HttpResponse(null, { status: 500 }), { once: true }),
      http.get(PART("/laps"), () => HttpResponse.json(DEBRIEF_R19.laps)),
    );
    const { user } = await renderPage();

    expect(await screen.findByText("Lap leaders unavailable")).toBeInTheDocument();
    expect(screen.getByText("Race trace unavailable")).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: "7 drivers penalised" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 1 })).toBeInTheDocument();

    await user.click(screen.getAllByRole("button", { name: "Retry" })[0]);
    expect(await screen.findByRole("heading", { name: "Verstappen led from lap 44 to the flag" })).toBeInTheDocument();
  });

  it("says why a race is not classified, with nothing invented", async () => {
    server.use(
      http.get(PART(""), () =>
        HttpResponse.json({
          ...DEBRIEF_R19.summary,
          available: false,
          reason: "The race hasn't been classified yet.",
          classification: [],
          titles: [],
        }),
      ),
    );
    await renderPage();

    expect(await screen.findByText("The race hasn't been classified yet.")).toBeInTheDocument();
    expect(screen.queryByText("Winning margin")).not.toBeInTheDocument();
    expect(screen.queryByText(/Classification: /)).not.toBeInTheDocument();
  });

  it("says the calendar could not load, and tries again", async () => {
    server.use(
      http.get(SCHEDULE_URL, () => new HttpResponse(null, { status: 500 }), { once: true }),
      http.get(SCHEDULE_URL, () => HttpResponse.json(SEASON_2026.schedule)),
    );
    const { user } = await renderPage({ schedule: Promise.resolve(null) });

    expect(await screen.findByText("The race calendar couldn't load.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByRole("group", { name: "Podium" })).toBeInTheDocument();
  });

  it("waits for the first debrief before a race has been classified", async () => {
    const upcoming = SEASON_2026.schedule.map((race) => ({ ...race, status: "upcoming" }));
    server.use(http.get(SCHEDULE_URL, () => HttpResponse.json(upcoming)));
    await renderPage({ schedule: Promise.resolve(upcoming), summary: Promise.resolve(null) });

    const hero = await screen.findByRole("heading", { level: 1, name: "Debriefs" });
    expect(hero).toBeInTheDocument();
    expect(
      within(hero.closest("header")!).getByText("The first debrief appears once a race of the season is classified."),
    ).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "How the race unfolded" })).not.toBeInTheDocument();
  });
});
