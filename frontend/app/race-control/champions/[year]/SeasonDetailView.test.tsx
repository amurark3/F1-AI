import { act, screen, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useServerStatus, type ServerState } from "@/app/hooks/useServerStatus";
import type { SeasonDetail } from "@/app/lib/server/champions";
import { f1, rc } from "@/app/ui/tokens";
import { DIRECTORY_2026 } from "@/test/fixtures";
import { CHAMPIONS } from "@/test/fixtures/champions";
import { apiUrl, server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";

import { SeasonDetailView } from "./SeasonDetailView";

vi.mock("@/app/hooks/useServerStatus", () => ({ useServerStatus: vi.fn() }));

const clinched = CHAMPIONS.season2026;
const fangio = CHAMPIONS.season1957;
const driver = clinched.driver_champion!;

// Derived from season2026 with f1db's standings after R18 (the title not yet decided).
const open: SeasonDetail = {
  ...clinched,
  rounds_completed: 18,
  decided_at: null,
  race_winners: clinched.race_winners!.filter((w) => w.round <= 18),
  driver_champion: { ...driver, points: 365, wins: 9, title_decided: false },
  runner_up: { name: "George Russell", last_name: "Russell", points: 242 },
  constructor_champion: { name: "Mercedes", points: 607, title_decided: false },
};
// Derived from season2026: 20 rounds, all run, so the title is final.
const final: SeasonDetail = { ...clinched, round_count: 20 };
// Derived from season2026: nothing recorded yet.
const none: SeasonDetail = {
  ...clinched,
  driver_champion: null,
  runner_up: null,
  constructor_champion: null,
  race_winners: [],
  rounds_completed: 0,
  decided_at: null,
};

async function renderView(
  detail: SeasonDetail | null,
  { year = 2026, latest = 2026, seed = Promise.resolve(detail) } = {},
) {
  server.use(http.get(apiUrl(`/api/champions/${year}`), () => HttpResponse.json(detail ?? { error: "not found" })));
  let view!: ReturnType<typeof renderWithProviders>;
  await act(() => {
    view = renderWithProviders(<SeasonDetailView year={year} latest={latest} seed={seed} />);
    return Promise.resolve();
  });
  return view;
}

describe("SeasonDetailView", () => {
  beforeEach(() => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date("2026-11-18T12:00:00Z"));
    vi.mocked(useServerStatus).mockReturnValue({ status: "ready" } as ServerState);
    server.use(http.get(apiUrl("/api/profiles/:year/directory"), () => HttpResponse.json(DIRECTORY_2026)));
  });
  afterEach(() => vi.useRealTimers());

  it("opens on the clinched champion in gold, with four tiles and the crumbs", async () => {
    const { container } = await renderView(clinched);

    expect(await screen.findByRole("heading", { level: 1, name: "Kimi Antonelli" })).toBeInTheDocument();
    expect(screen.getByText("2026 World Champion · clinched")).toHaveClass("text-rc-gold");
    expect(container.querySelector("[data-hero-rule]")).toHaveStyle({ backgroundColor: rc.gold });
    expect(
      screen.getByText("Mercedes · Title decided in round 19, Mexico City. 3 rounds still to run."),
    ).toBeInTheDocument();
    expect(screen.getByText("after round 20 of 23")).toBeInTheDocument();
    expect(screen.getByText("over Max Verstappen · 279 pts")).toBeInTheDocument();
    expect(screen.getByText("652 pts after round 20 of 23")).toBeInTheDocument();
    expect(screen.getByText("20 of 23 rounds")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "2025 season" })).toHaveAttribute("href", "/race-control/champions/2025");
    expect(screen.queryByRole("link", { name: "2027 season" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: /All champions/ })).toHaveAttribute("href", "/race-control/champions");
  });

  it("draws the round-by-round card with the decider's flag", async () => {
    await renderView(clinched);

    const ribbon = await screen.findByRole("list", {
      name: "2026, round by round: 9 wins for Antonelli, decided with 4 rounds to spare",
    });
    expect(within(ribbon).getAllByRole("listitem")).toHaveLength(23);
    expect(within(ribbon).getByText("Title decided · Mexico City")).toBeInTheDocument();
    expect(within(ribbon).getByText("R21 · still to run")).toBeInTheDocument();
    expect(screen.getByRole("list", { name: "Legend" })).toHaveTextContent(
      "Antonelli's winTitle decidedStill to runBar = the winning car's team",
    );
  });

  it("lists every winner with dates, the decider tag, links and the rounds still to run", async () => {
    await renderView(clinched);

    const rows = within(await screen.findByRole("list", { name: "2026 race winners" })).getAllByRole("listitem");
    expect(rows).toHaveLength(21);
    expect(rows[0]).toHaveTextContent("R1George RussellMercedes · Formula 1 Qatar Airways Australian Grand Prix 2026");
    expect(rows[0]).toHaveTextContent("8 Mar");
    expect(await within(rows[0]).findByRole("link", { name: "George Russell" })).toBeInTheDocument();
    expect(within(rows[18]).getByText("Title decided")).toBeInTheDocument();
    expect(rows[18]).toHaveTextContent("1 Nov");
    expect(rows[20]).toHaveTextContent("R21–R233 rounds still to run");
    expect(screen.getByText("Source: f1db · 2026 after round 20 of 23")).toBeInTheDocument();
  });

  it("folds a shared drive and leaves a past season unlinked", async () => {
    await renderView(fangio, { year: 1957 });

    expect(await screen.findByRole("heading", { level: 1, name: "Juan Manuel Fangio" })).toBeInTheDocument();
    expect(screen.getByText("1957 World Champion")).toBeInTheDocument();
    expect(screen.getByText("final total")).toBeInTheDocument();
    expect(screen.getByText("title awarded from 1958")).toBeInTheDocument();
    const rows = within(screen.getByRole("list", { name: "1957 race winners" })).getAllByRole("listitem");
    expect(rows).toHaveLength(8);
    expect(rows[4]).toHaveTextContent("Tony Brooks / Stirling Moss");
    expect(rows[4]).toHaveTextContent("Shared drive");
    expect(rows[4]).toHaveTextContent("20 Jul");
    expect(within(rows[5]).getByText("Title decided")).toBeInTheDocument();
    expect(screen.queryByText(/still to run/)).not.toBeInTheDocument();
    expect(screen.getByText("Source: f1db")).toBeInTheDocument();
    expect(screen.queryAllByRole("link", { name: /Brooks|Moss|Maserati|Vanwall/ })).toHaveLength(0);
    expect(screen.getByRole("link", { name: "1956 season" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "1958 season" })).toBeInTheDocument();
  });

  it("shows no stepper link before the first season", async () => {
    await renderView(fangio, { year: 1950 });
    expect(screen.queryByRole("link", { name: "1949 season" })).not.toBeInTheDocument();
  });

  it("keeps gold off an open title: a leader is not a champion", async () => {
    const { container } = await renderView(open);

    expect(await screen.findByText("2026 championship leader")).not.toHaveClass("text-rc-gold");
    expect(container.querySelector("[data-hero-rule]")).toHaveStyle({ backgroundColor: f1.red });
    expect(screen.getByText("Mercedes · Leads after round 18 of 23; the title is still open.")).toBeInTheDocument();
    expect(screen.getByText("Constructors' leader")).toBeInTheDocument();
    expect(screen.getByText("Lead")).toBeInTheDocument();
    expect(screen.getByText("9 wins for Antonelli, title still open after round 18")).toBeInTheDocument();
    expect(screen.getByText("R19–R23")).toBeInTheDocument();
    expect(screen.getByText("5 rounds still to run")).toBeInTheDocument();
    expect(screen.queryByRole("list", { name: "Legend" })).toHaveTextContent("Antonelli's winStill to run");
    expect(container.querySelector(".text-rc-gold")).toBeNull();
  });

  it("opens the flag the other way early in a season and copes with a winner who has no team", async () => {
    const [first, ...rest] = clinched.race_winners!;
    await renderView({
      ...clinched,
      decided_at: { round: 5, date: "2026-05-01", place: "Miami" },
      race_winners: [{ ...first, team: null, team_id: null }, ...rest],
    });

    const flag = await screen.findByText("Title decided · Miami");
    expect(flag).toHaveClass("left-1/2");
    const rows = within(screen.getByRole("list", { name: "2026 race winners" })).getAllByRole("listitem");
    expect(rows[0]).toHaveTextContent("R1George RussellFormula 1");
  });

  it("reads final once every round has run", async () => {
    await renderView(final);

    expect(await screen.findByText("final total")).toBeInTheDocument();
    expect(screen.getByText("652 pts")).toBeInTheDocument();
    expect(screen.getByText(/decided with 1 round to spare/)).toBeInTheDocument();
    expect(screen.queryByText(/still to run/)).not.toBeInTheDocument();
  });

  it("says so when no champion or race is recorded", async () => {
    const { container } = await renderView(none);

    expect(await screen.findByRole("heading", { level: 1, name: "No champion recorded" })).toBeInTheDocument();
    expect(screen.getByText("2026 season")).toBeInTheDocument();
    expect(screen.getByText("No race has a result yet.")).toBeInTheDocument();
    expect(screen.getByText("R1–R23")).toBeInTheDocument();
    expect(screen.getByText("23 rounds still to run")).toBeInTheDocument();
    expect(screen.getByText("Source: f1db")).toBeInTheDocument();
    expect(screen.queryByText("Round by round")).not.toBeInTheDocument();
    expect(container.querySelector("[data-lead]")).toBeNull();
  });

  it("shows only the constructors' tile when no driver has a title", async () => {
    await renderView({ ...none, constructor_champion: clinched.constructor_champion });
    expect(await screen.findByText("Constructors' champion")).toBeInTheDocument();
    expect(screen.queryByText("Points")).not.toBeInTheDocument();
  });

  it("keeps the crumbs and a heading while the data is on its way", async () => {
    const { container } = await renderView(clinched, { seed: new Promise(() => undefined) });

    expect(screen.getByRole("heading", { level: 1, name: "2026 season" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "2025 season" })).toBeInTheDocument();
    expect(container.querySelectorAll('[class*="animate-pulse"]')).toHaveLength(3);
  });

  it("fetches for itself when the server had nothing", async () => {
    await renderView(clinched, { seed: Promise.resolve(null) });
    expect(await screen.findByRole("heading", { level: 1, name: "Kimi Antonelli" })).toBeInTheDocument();
  });

  it("fails each section on its own, with the heading and crumbs kept", async () => {
    await renderView(null);

    expect(await screen.findAllByText("2026 season unavailable")).toHaveLength(3);
    expect(screen.getByRole("heading", { level: 1, name: "2026 season" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /All champions/ })).toBeInTheDocument();
  });
});
