import { act, fireEvent, screen, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useServerStatus, type ServerState } from "@/app/hooks/useServerStatus";
import { DIRECTORY_2026, SEASON_2026 } from "@/test/fixtures";
import { REWIND_R19 as r19 } from "@/test/fixtures/rewind";
import { change, driver, finalOf, lap, race } from "@/test/fixtures/rewindHandBuilt";
import { apiUrl, server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";

import { Rewind } from "./Rewind";

import type { RaceRewind, RewindResponse } from "./rewindTypes";

const nav = vi.hoisted(() => ({ search: "round=19", replace: vi.fn() }));

vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(nav.search),
  useRouter: () => ({ replace: nav.replace }),
  usePathname: () => "/race-control/rewind",
}));
vi.mock("@/app/hooks/useServerStatus", () => ({ useServerStatus: vi.fn() }));

const SCHEDULE_URL = apiUrl("/api/schedule/2026");
const REWIND_URL = apiUrl("/api/race-control/rewind/:year/:round");

function serve(payload: RewindResponse | Record<string, unknown>) {
  server.use(http.get(REWIND_URL, () => HttpResponse.json(payload)));
}

async function renderPage(search = "round=19", schedule: unknown = SEASON_2026.schedule) {
  nav.search = search;
  let rendered: ReturnType<typeof renderWithProviders> | undefined;
  await act(() => {
    rendered = renderWithProviders(
      <Rewind year={2026} seeds={{ schedule: Promise.resolve(schedule as typeof SEASON_2026.schedule) }} />,
    );
    return Promise.resolve();
  });
  return rendered!;
}

const heading = (name: string | RegExp, level = 3) => screen.findByRole("heading", { level, name });
const texts = (nodes: Iterable<Element>) => Array.from(nodes, (node) => node.textContent);

/** The tower's rows: place, code, then the tag text. */
function towerCodes(container: HTMLElement): string[] {
  return texts(container.querySelector("ol")!.querySelectorAll("li > b"));
}

function rowOf(container: HTMLElement, code: string): HTMLElement {
  const row = Array.from(container.querySelector("ol")!.querySelectorAll("li")).find(
    (li) => li.querySelector("b")?.textContent === code,
  );
  return row as HTMLElement;
}

function changeRows(container: HTMLElement): HTMLElement[] {
  return Array.from(container.querySelectorAll<HTMLElement>("figure ul:not([aria-label]) > li"));
}

describe("Race Rewind", () => {
  beforeEach(() => {
    nav.search = "round=19";
    nav.replace.mockClear();
    vi.mocked(useServerStatus).mockReturnValue({ status: "ready" } as ServerState);
    server.use(
      http.get(apiUrl("/api/profiles/:year/directory"), () => HttpResponse.json(DIRECTORY_2026)),
      http.get(SCHEDULE_URL, () => HttpResponse.json(SEASON_2026.schedule)),
      http.get(apiUrl("/api/champions/:year"), () => HttpResponse.json(SEASON_2026.winners)),
    );
    serve(r19);
  });

  it("opens on lap 44 of Mexico City: hero, scrubber, chart, tower, changes and the final card", async () => {
    const { container } = await renderPage();

    expect(
      await screen.findByRole("heading", { level: 1, name: "The lead changed twice, both times at a stop" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Race Rewind · Round 19 · Mexico City GP")).toBeInTheDocument();
    expect(
      await screen.findByText(
        "Leclerc led to lap 27, Antonelli to lap 43, Verstappen from lap 44 to the flag. Drag the scrubber to replay the order at the line, lap by lap; the last step is the FIA final classification.",
      ),
    ).toBeInTheDocument();
    const range = screen.getByRole("slider", { name: "Lap" });
    expect(range).toHaveValue("44");
    expect(range).toHaveAttribute("max", "72");
    expect(range).toHaveAttribute("aria-valuetext", "After lap 44 of 71");
    expect(screen.getByText("Safety Car")).toBeInTheDocument();
    expect(await heading("Verstappen led every lap from 44")).toBeInTheDocument();
    expect(await screen.findByText("Order after lap 44")).toBeInTheDocument();
    expect(await heading("Verstappen leads; Antonelli stopped")).toBeInTheDocument();
    expect(towerCodes(container).join(" ")).toBe(
      "VER LEC HAM ANT NOR RUS PIA LIN COL GAS HUL BEA BOR HAD LAW SAI HIR ALB PER BOT ALO STR",
    );
    for (const code of ["HAM", "ANT", "RUS", "PIA", "GAS", "PER", "HIR"]) {
      expect(within(rowOf(container, code)).getByText("PIT")).toBeInTheDocument();
    }
    expect(container.querySelectorAll("ol > li")).toHaveLength(22 + 17);
    expect(within(rowOf(container, "BOT")).getByText("DNF L42")).toBeInTheDocument();
    expect(within(rowOf(container, "ALO")).getByText("DNF L5")).toBeInTheDocument();
    expect(within(rowOf(container, "STR")).getByText("DNF L5")).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 2, name: "What changed on lap 44" })).toBeInTheDocument();
  });

  it("explains the six changes of lap 44", async () => {
    const { container } = await renderPage();

    expect(await heading("Antonelli's stop moved the top four")).toBeInTheDocument();
    const rows = changeRows(container);
    expect(rows).toHaveLength(6);
    const read = (row: HTMLElement) => row.textContent ?? "";
    expect(read(rows[0])).toContain("Max Verstappen");
    expect(read(rows[0])).toContain("P2 → P1");
    expect(read(rows[0])).toContain("A rival's stop");
    expect(read(rows[0])).toContain("Antonelli stopped lap 43");
    expect(read(rows[2])).toMatch(/Lewis Hamilton.*P4 → P3.*Own stop.*stopped lap 44/);
    expect(read(rows[3])).toMatch(/P1 → P4.*Own stop.*stopped lap 43/);
    expect(read(rows[4])).toMatch(/Albon|Alexander Albon/);
    expect(read(rows[4])).toMatch(/P19 → P18.*A rival's stop.*Pérez stopped lap 43/);
    expect(read(rows[5])).toMatch(/P18 → P19.*Own stop.*stopped lap 43/);
  });

  it("shows the road order against the FIA's, with each penalty's document", async () => {
    const { container } = await renderPage();

    expect(await heading("Three post-race penalties reshuffled 7th to 17th")).toBeInTheDocument();
    const final = container.querySelectorAll("ol")[1];
    const line = (code: string) =>
      Array.from(final.querySelectorAll("li")).find((li) => li.textContent?.includes(code))?.textContent;
    expect(line("PIA")).toContain("road P7");
    expect(line("PIA")).toContain("10 s · FIA doc 79");
    expect(line("COL")).toContain("road P8");
    expect(line("COL")).toContain("10 s · FIA doc 85");
    expect(line("GAS")).toContain("road P10");
    expect(line("GAS")).toContain("30 s · FIA doc 84");
    expect(line("LAW")).toContain("road P9");
    expect(final.querySelectorAll("li")).toHaveLength(17);
    const link = screen.getByRole("link", { name: "doc 86" });
    expect(link).toHaveAttribute("href", r19.final!.url);
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
  });

  it("opens on the final classification for ?lap=final", async () => {
    const { container } = await renderPage("round=19&lap=final");

    expect(await heading("Verstappen wins")).toBeInTheDocument();
    expect(towerCodes(container).join(" ")).toBe(
      "VER HAM ANT LEC NOR RUS LAW BOR HAD HIR ALB SAI PIA HUL COL PER GAS LIN BEA BOT STR ALO",
    );
    expect(within(rowOf(container, "LIN")).getByText("DNF L58")).toBeInTheDocument();
    expect(within(rowOf(container, "BEA")).getByText("DNF L47")).toBeInTheDocument();
    expect(screen.getAllByText("Final").length).toBeGreaterThan(1);
    expect(screen.getByRole("heading", { level: 2, name: "What changed after the flag" })).toBeInTheDocument();
    expect(screen.getByText(/The flag fell on lap 71/)).toBeInTheDocument();
    expect(screen.getByRole("slider", { name: "Lap" })).toHaveAttribute("aria-valuetext", "Final classification");
  });

  it("opens on the grid for ?lap=0", async () => {
    const { container } = await renderPage("round=19&lap=0");

    expect(await heading("Hamilton on pole")).toBeInTheDocument();
    expect(screen.getByText("FIA final starting grid (doc 67)")).toBeInTheDocument();
    const law = rowOf(container, "LAW");
    expect(within(law).getByText("Pit lane")).toBeInTheDocument();
    expect(law.querySelector("span")?.textContent).toBe("–");
    expect(screen.getByRole("heading", { level: 2, name: "What changed at the start" })).toBeInTheDocument();
    expect(screen.getByText("The race hasn't started at this step: this is the starting grid.")).toBeInTheDocument();
  });

  it("opens on the road order for ?lap=71", async () => {
    const { container } = await renderPage("round=19&lap=71");

    expect(await screen.findByText("Order after lap 71")).toBeInTheDocument();
    expect(towerCodes(container).slice(0, 17).join(" ")).toBe(
      "VER HAM ANT LEC NOR RUS PIA COL LAW GAS BOR HAD HIR ALB SAI HUL PER",
    );
  });

  it("reads lap 1, lap 28, lap 45 under the red flag, lap 8 under the VSC and lap 59 behind a retirement", async () => {
    const first = await renderPage("round=19&lap=1");
    expect(await heading("Leclerc took the lead from Hamilton")).toBeInTheDocument();
    expect(screen.getByText("+/− = places vs the grid")).toBeInTheDocument();
    first.unmount();

    const second = await renderPage("round=19&lap=28");
    expect(await heading("Antonelli leads; Leclerc stopped")).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 3, name: "Leclerc's stop moved the top six" })).toBeInTheDocument();
    second.unmount();

    const red = await renderPage("round=19&lap=45");
    expect((await screen.findAllByText("Red flag")).length).toBeGreaterThan(0);
    const rows = changeRows(red.container);
    const perez = rows.find((row) => row.textContent?.includes("P18 → P19"));
    expect(perez?.textContent).toContain("Under red flag");
    expect(perez?.textContent).toContain("not counted as a pass");
    red.unmount();

    const vsc = await renderPage("round=19&lap=8");
    expect((await screen.findAllByText("VSC")).length).toBeGreaterThan(0);
    expect(changeRows(vsc.container).some((row) => row.textContent?.includes("Under VSC"))).toBe(true);
    vsc.unmount();

    const late = await renderPage("round=19&lap=59");
    expect((await screen.findAllByText("Safety Car")).length).toBeGreaterThan(0);
    const retired = changeRows(late.container).filter((row) => row.textContent?.includes("Retirement ahead"));
    expect(retired).toHaveLength(7);
    expect(retired[0].textContent).toContain("Lindblad retired");
  });

  it("ignores a lap the race does not have or one that is no number", async () => {
    for (const search of ["round=19&lap=99", "round=19&lap=x"]) {
      const { unmount } = await renderPage(search);
      expect(await screen.findByText("Order after lap 44")).toBeInTheDocument();
      unmount();
    }
  });

  it("moves with the buttons and the range, and writes each step to the URL without navigating", async () => {
    const write = vi.spyOn(window.history, "replaceState");
    const { user } = await renderPage();
    await screen.findByText("Order after lap 44");

    await user.click(screen.getByRole("button", { name: "Next lap" }));
    expect(await screen.findByText("Order after lap 45")).toBeInTheDocument();
    expect(write).toHaveBeenLastCalledWith(null, "", "/race-control/rewind?round=19&lap=45");
    await user.click(screen.getByRole("button", { name: "Previous lap" }));
    expect(await screen.findByText("Order after lap 44")).toBeInTheDocument();
    fireEvent.change(screen.getByRole("slider", { name: "Lap" }), { target: { value: "72" } });
    expect(await heading("Verstappen wins")).toBeInTheDocument();
    expect(write).toHaveBeenLastCalledWith(null, "", "/race-control/rewind?round=19&lap=final");
    expect(screen.getByRole("button", { name: "Next lap" })).toBeDisabled();
    fireEvent.change(screen.getByRole("slider", { name: "Lap" }), { target: { value: "0" } });
    expect(await heading("Hamilton on pole")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Previous lap" })).toBeDisabled();
    expect(nav.replace).not.toHaveBeenCalled();
  });

  it("plays on from the grid, one step at a time, and a manual move pauses it", async () => {
    await renderPage("round=19&lap=0");
    await heading("Hamilton on pole");
    vi.useFakeTimers({ toFake: ["setInterval", "clearInterval"] });
    try {
      fireEvent.click(screen.getByRole("button", { name: "▶ Play" }));
      expect(screen.getByRole("button", { name: "❚❚ Pause" })).toHaveAttribute("aria-pressed", "true");
      act(() => void vi.advanceTimersByTime(600));
      expect(screen.getByRole("slider", { name: "Lap" })).toHaveValue("1");
      act(() => void vi.advanceTimersByTime(1200));
      expect(screen.getByRole("slider", { name: "Lap" })).toHaveValue("3");
      fireEvent.click(screen.getByRole("button", { name: "Next lap" }));
      expect(screen.getByRole("button", { name: "▶ Play" })).toBeInTheDocument();
      act(() => void vi.advanceTimersByTime(3000));
      expect(screen.getByRole("slider", { name: "Lap" })).toHaveValue("4");
    } finally {
      vi.useRealTimers();
    }
  });

  it("lists completed rounds only and writes the picked round to the URL", async () => {
    nav.search = "round=20";
    const { user } = await renderPage("round=20");

    expect(await screen.findByRole("button", { name: "Next round" })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "Previous round" }));
    expect(nav.replace).toHaveBeenCalledWith("/race-control/rewind?round=19", { scroll: false });
  });

  it("loads the historical season in the URL and keeps it when scrubbing", async () => {
    server.use(http.get(apiUrl("/api/schedule/2025"), () => HttpResponse.json(SEASON_2026.schedule)));
    const write = vi.spyOn(window.history, "replaceState");
    const { user } = await renderPage("round=19&year=2025");

    expect(await screen.findByRole("group", { name: "2025 race picker" })).toBeInTheDocument();
    await user.click(await screen.findByRole("button", { name: "Next lap" }));
    expect(write).toHaveBeenCalledWith(null, "", "/race-control/rewind?round=19&year=2025&lap=45");
  });

  it("says the calendar could not load, and tries again", async () => {
    server.use(
      http.get(SCHEDULE_URL, () => new HttpResponse(null, { status: 500 }), { once: true }),
      http.get(SCHEDULE_URL, () => HttpResponse.json(SEASON_2026.schedule)),
    );
    const { user } = await renderPage("round=19", null);

    expect(await screen.findByText("The race calendar couldn't load.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByText("Order after lap 44")).toBeInTheDocument();
  });

  it("waits for the first rewind before a race has been classified", async () => {
    const upcoming = SEASON_2026.schedule.map((race) => ({ ...race, status: "upcoming" }));
    server.use(http.get(SCHEDULE_URL, () => HttpResponse.json(upcoming)));
    await renderPage("round=19", upcoming);

    expect(await screen.findByRole("heading", { level: 1, name: "Race Rewind" })).toBeInTheDocument();
    expect(screen.getByText("The first rewind appears once a race of the season is classified.")).toBeInTheDocument();
  });

  it("says why a race has no rewind, and what failed", async () => {
    serve({ year: 2026, round: 19, available: false, reason: "OpenF1 hasn't published this race's laps yet." });
    const first = await renderPage();
    expect(await screen.findByRole("heading", { level: 1, name: "Mexico City Grand Prix" })).toBeInTheDocument();
    expect(screen.getByText("OpenF1 hasn't published this race's laps yet.")).toBeInTheDocument();
    first.unmount();

    serve({ year: 2026, round: 19, available: false, reason: null });
    await renderPage();
    expect(await screen.findByRole("heading", { level: 1, name: "Mexico City Grand Prix" })).toBeInTheDocument();
  });

  it("reports a failed fetch and recovers on retry", async () => {
    server.use(
      http.get(REWIND_URL, () => HttpResponse.json({ available: false, reason: null, error: "boom", error_id: "x" }), {
        once: true,
      }),
    );
    const { user } = await renderPage();

    expect(await screen.findByText("Race Rewind unavailable")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByText("Order after lap 44")).toBeInTheDocument();
  });
});

describe("Race Rewind on other races", () => {
  beforeEach(() => {
    nav.search = "round=19";
    vi.mocked(useServerStatus).mockReturnValue({ status: "ready" } as ServerState);
    server.use(
      http.get(apiUrl("/api/profiles/:year/directory"), () => HttpResponse.json(DIRECTORY_2026)),
      http.get(SCHEDULE_URL, () => HttpResponse.json(SEASON_2026.schedule)),
      http.get(apiUrl("/api/champions/:year"), () => HttpResponse.json(SEASON_2026.winners)),
    );
  });

  /** Hand-built: three cars, one leader all race, the default step is lap 1. */
  it("opens on lap 1 when one driver led every lap", async () => {
    serve(race());
    await renderPage();

    expect(await screen.findByRole("heading", { level: 1, name: "Alfa Alpha led every lap" })).toBeInTheDocument();
    expect(screen.getByRole("slider", { name: "Lap" })).toHaveValue("1");
    expect(await heading("No position changes on lap 1")).toBeInTheDocument();
    expect(screen.getByText("Position changes · lap 1")).toBeInTheDocument();
  });

  /** Hand-built: no classification is published, so there is no Final step. */
  it("has no Final step before a classification is published", async () => {
    serve(race({ final: null }));
    await renderPage();

    expect(await heading("Not classified yet")).toBeInTheDocument();
    expect(
      screen.getByText("The classification isn't published yet; the Final step appears when it is."),
    ).toBeInTheDocument();
    expect(screen.getByRole("slider", { name: "Lap" })).toHaveAttribute("max", "3");
  });
});

describe("Race Rewind on hand-built races", () => {
  beforeEach(() => {
    nav.search = "round=19&lap=2";
    vi.mocked(useServerStatus).mockReturnValue({ status: "ready" } as ServerState);
    server.use(
      http.get(apiUrl("/api/profiles/:year/directory"), () => HttpResponse.json(DIRECTORY_2026)),
      http.get(SCHEDULE_URL, () => HttpResponse.json(SEASON_2026.schedule)),
      http.get(apiUrl("/api/champions/:year"), () => HttpResponse.json(SEASON_2026.winners)),
    );
  });

  const withLap2 = (changes: Array<ReturnType<typeof change>>, over: Partial<RaceRewind> = {}): RaceRewind =>
    race({
      drivers: [driver("AAA"), driver("BBB"), driver("CCC")],
      laps: [lap(1, ["AAA", "BBB", "CCC"]), lap(2, ["AAA", "CCC", "BBB"], { changes }), lap(3, ["AAA", "CCC", "BBB"])],
      ...over,
    });

  it("labels a pass and a pass the other way, and a change nothing explains", async () => {
    serve(
      withLap2([
        change("CCC", 3, 2, { kind: "pass", rival: "BBB" }),
        change("BBB", 2, 3, { kind: "pass", rival: "CCC" }),
        change("AAA", 1, 1, { kind: "change" }),
      ]),
    );
    const { container } = await renderPage("round=19&lap=2");

    expect(await heading("3 position changes: 2 passes, 1 other")).toBeInTheDocument();
    const rows = changeRows(container);
    expect(rows[0].textContent).toMatch(/Pass.*passed Bravo Bell/);
    expect(rows[1].textContent).toMatch(/Pass.*passed by Cole Carter/);
    expect(rows[2].textContent).toContain("Position change");
  });

  it("shows a provisional OpenF1 classification without a document link", async () => {
    serve(
      withLap2([], {
        final: finalOf({ source: "openf1-session-result", provisional: true, document: null, url: null }),
      }),
    );
    await renderPage("round=19&lap=final");

    expect(await screen.findAllByText("Provisional")).not.toHaveLength(0);
    expect(screen.getByText(/against the provisional classification/)).toBeInTheDocument();
    expect(screen.getByText(/final order: OpenF1 session result, provisional/)).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /doc/ })).not.toBeInTheDocument();
    expect(screen.getByText(/OpenF1's provisional classification\./)).toBeInTheDocument();
  });

  it("names an FIA document it has no link for in plain text", async () => {
    serve(withLap2([], { final: finalOf({ url: null }) }));
    await renderPage();

    expect(await screen.findByText(/final order: FIA final classification \(doc 86\)/)).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "doc 86" })).not.toBeInTheDocument();
  });

  it("tags a DSQ, a DNS and a not-classified car at the final step, and lists only the classified on the card", async () => {
    const final = finalOf({
      rows: [
        { driver_code: "AAA", position: 1, status: "finished", laps: 3, road_position: null, penalties: [] },
        { driver_code: "BBB", position: null, status: "dsq", laps: 3, road_position: 2, penalties: [] },
        { driver_code: "CCC", position: null, status: "dns", laps: null, road_position: null, penalties: [] },
        { driver_code: "DDD", position: null, status: "not_classified", laps: 1, road_position: null, penalties: [] },
      ],
    });
    serve(withLap2([], { final, drivers: [driver("AAA"), driver("BBB"), driver("CCC"), driver("DDD")] }));
    const { container } = await renderPage("round=19&lap=final");

    expect(await screen.findByText("DSQ")).toBeInTheDocument();
    expect(screen.getByText("DNS")).toBeInTheDocument();
    expect(screen.getByText("NC")).toBeInTheDocument();
    expect(container.querySelectorAll("ol")[1].querySelectorAll("li")).toHaveLength(1);
    expect(screen.getByText("The road order stood")).toBeInTheDocument();
  });

  it("starts from a grid of OpenF1 positions or of f1db", async () => {
    serve(
      withLap2([], { grid: { order: ["AAA", "BBB", "CCC"], pit_lane: [], source: "openf1-position", document: null } }),
    );
    const first = await renderPage("round=19&lap=0");
    expect(await screen.findByText("Order at the start, from OpenF1 positions")).toBeInTheDocument();
    first.unmount();

    serve(withLap2([], { grid: { order: ["AAA", "BBB", "CCC"], pit_lane: [], source: "f1db", document: null } }));
    await renderPage("round=19&lap=0");
    expect(await screen.findByText("Official grid (f1db)")).toBeInTheDocument();
  });

  it("marks a retirement-led lead change", async () => {
    const laps = [
      lap(1, ["AAA", "BBB", "CCC"]),
      lap(2, ["BBB", "CCC"], { changes: [change("BBB", 2, 1, { kind: "retirement", rival: "AAA" })] }),
      lap(3, ["BBB", "CCC"]),
    ];
    serve(withLap2([], { laps, drivers: [driver("AAA", { status: "dnf", laps: 1 }), driver("BBB"), driver("CCC")] }));
    await renderPage("round=19&lap=2");

    expect(await heading("Bravo Bell leads; Alfa Alpha retired")).toBeInTheDocument();
    expect(screen.getByText("Alfa Alpha retired")).toBeInTheDocument();
  });
});
