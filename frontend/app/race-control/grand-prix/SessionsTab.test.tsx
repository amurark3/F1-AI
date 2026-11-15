import { screen, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it } from "vitest";

import { DIRECTORY_2026, WEEKEND_SESSIONS_2026 } from "@/test/fixtures";
import { apiUrl, server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";

import { SessionsTab } from "./SessionsTab";
import { PracticeTable, QualifyingTable, RaceTable } from "./SessionTables";

import type { WeekendSessionsResponse } from "./sessionsModel";

function show(data: WeekendSessionsResponse | undefined, loading = false) {
  return renderWithProviders(<SessionsTab data={data} loading={loading} />);
}

describe("SessionsTab", () => {
  beforeEach(() => {
    server.use(http.get(apiUrl("/api/profiles/:year/directory"), () => HttpResponse.json(DIRECTORY_2026)));
  });

  it("opens on qualifying: official in-part gaps, DSQ tags, cut lines, no Team column", () => {
    show(WEEKEND_SESSIONS_2026.mexicoCity);

    expect(screen.getByRole("heading", { name: "Lewis Hamilton takes pole by 0.009 s" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Gap in their part" })).toBeInTheDocument();
    expect(screen.queryByRole("columnheader", { name: "Team" })).not.toBeInTheDocument();
    const norris = screen.getByRole("row", { name: /NOR|Norris/ });
    expect(norris).toHaveTextContent("+0.310");
    expect(norris).not.toHaveTextContent("+0.214");
    expect(screen.getAllByText("Up 1 · LAW DSQ")).toHaveLength(2);
    expect(screen.getByRole("row", { name: /HUL|lkenberg/ })).toHaveTextContent("+0.578");
    expect(screen.getByRole("row", { name: /ALB|Albon/ })).toHaveTextContent("+1.289");
    expect(screen.getByText("Knocked out in Q2")).toBeInTheDocument();
    expect(screen.getByText("Knocked out in Q1")).toBeInTheDocument();
    const cut = screen.getByText("Disqualified from qualifying");
    expect(cut).toHaveClass("text-rc-red-text");
    expect(screen.getByRole("row", { name: /^DSQ/ })).toHaveTextContent("Lawson");
    expect(screen.getByText("POLE")).toBeInTheDocument();
    expect(screen.getByText("One decision changed this order")).toBeInTheDocument();
    expect(screen.getByText("Fastest in each part")).toBeInTheDocument();
    expect(screen.getByText("Norris", { exact: false, selector: "div span:nth-child(2)" })).toBeInTheDocument();
    expect(screen.getAllByText("Final").length).toBeGreaterThan(0);
  });

  it("marks the fastest lap of each part purple and nothing else", () => {
    show(WEEKEND_SESSIONS_2026.mexicoCity);

    const hamilton = screen.getByRole("row", { name: /HAM|Hamilton/ });
    expect(within(hamilton).getAllByText("1:16.514")[0]).toHaveClass("text-(--f1-sector-best)");
    expect(within(hamilton).getByText("1:16.953")).not.toHaveClass("text-(--f1-sector-best)");
  });

  it("shows FP1 with nine stand-ins, each naming whose car it was, and keeps laps", async () => {
    const { user } = show(WEEKEND_SESSIONS_2026.mexicoCity);

    await user.click(screen.getByRole("radio", { name: "FP1" }));

    expect(screen.getByRole("heading", { name: "Charles Leclerc fastest in Free Practice 1" })).toBeInTheDocument();
    expect(screen.getByText(/9 cars driven by a stand-in/)).toBeInTheDocument();
    expect(screen.getAllByText(/FP1 run ·/)).toHaveLength(9);
    expect(screen.getByRole("columnheader", { name: "Laps" })).toBeInTheDocument();
    expect(screen.getByRole("row", { name: /VES|Vesti/ })).toHaveTextContent("FP1 run · Russell’s car");
    expect(screen.getByRole("row", { name: /LEC|Leclerc/ })).not.toHaveTextContent("run ·");
  });

  it("names the session when no car is classified first, and counts a single stand-in", () => {
    const fp1 = WEEKEND_SESSIONS_2026.mexicoCity.sessions[0];
    if (fp1?.kind !== "practice") throw new Error("fixture changed");
    const [first, , vesti] = fp1.entries;
    const unranked = { ...first, position: null, position_text: "NC" };
    const oneStandIn = { ...fp1, entries: [unranked, { ...vesti, position: 2 }] };
    show({ ...WEEKEND_SESSIONS_2026.mexicoCity, sessions: [oneStandIn] });

    expect(screen.getByRole("heading", { name: "Free Practice 1" })).toBeInTheDocument();
    expect(screen.getByText(/1 car driven by a stand-in/)).toBeInTheDocument();
  });

  it("says nothing about stand-ins when every car was driven by its regular", () => {
    const fp1 = WEEKEND_SESSIONS_2026.mexicoCity.sessions[0];
    if (fp1?.kind !== "practice") throw new Error("fixture changed");
    const regulars = { ...fp1, entries: fp1.entries.map((entry) => ({ ...entry, stand_in_for: null })) };
    show({ ...WEEKEND_SESSIONS_2026.mexicoCity, sessions: [regulars] });

    expect(screen.queryByText(/driven by a stand-in/)).not.toBeInTheDocument();
  });

  it("drops the sprint race and the sprint grid from the strip, keeping sprint qualifying", () => {
    show(WEEKEND_SESSIONS_2026.sprintWeekend);

    const group = screen.getByRole("radiogroup", { name: "Weekend session" });
    expect(
      within(group)
        .getAllByRole("radio")
        .map((r) => r.textContent),
    ).toEqual(["FP1", "SQ", "Qualifying"]);
  });

  it("says why there is nothing, and shows a loader while reading", () => {
    const { unmount } = show(WEEKEND_SESSIONS_2026.none);
    expect(screen.getByText(/No session results published for this round yet/)).toBeInTheDocument();
    unmount();

    const again = show(undefined);
    expect(screen.getByText(/appear here once the weekend has been run/)).toBeInTheDocument();
    again.unmount();

    show(undefined, true);
    expect(screen.getByText("Loading session results")).toBeInTheDocument();
  });

  it("shows a dash for every figure a row lacks", () => {
    const [fp1, , , qualifying] = WEEKEND_SESSIONS_2026.mexicoCity.sessions;
    const sprint = WEEKEND_SESSIONS_2026.sprintWeekend.sessions.find((s) => s.kind === "race");
    if (fp1?.kind !== "practice" || qualifying?.kind !== "qualifying" || sprint?.kind !== "race") {
      throw new Error("fixture changed");
    }
    const blank = { time: null, gap: null, laps: null, grid: null, retired: null, points: null };
    const { unmount } = renderWithProviders(<PracticeTable entries={[{ ...fp1.entries[0], ...blank }]} label="FP1" />);
    expect(screen.getAllByText("—")).toHaveLength(3);
    unmount();

    const none = { ...qualifying.entries[0], part: null, q1: null, q2: null, q3: null, part_gap: null };
    const quali = renderWithProviders(<QualifyingTable entries={[none]} />);
    expect(screen.getByText("No time set")).toBeInTheDocument();
    expect(screen.getAllByText("—").length).toBeGreaterThan(3);
    quali.unmount();

    const race = renderWithProviders(
      <RaceTable
        entries={[
          { ...sprint.entries[0], ...blank },
          { ...sprint.entries[1], ...blank, retired: "Collision" },
          { ...sprint.entries[2], ...blank, time: "1:30:00.000" },
        ]}
      />,
    );
    expect(screen.getByText("Collision")).toHaveClass("text-rc-red-text");
    expect(screen.getByText("1:30:00.000")).toBeInTheDocument();
    race.unmount();
  });

  it("falls back to the practice label when a table is given none, and draws a race table", () => {
    const fp1 = WEEKEND_SESSIONS_2026.mexicoCity.sessions[0];
    if (fp1?.kind !== "practice") throw new Error("fixture changed");
    const { unmount } = renderWithProviders(<PracticeTable entries={fp1.entries.slice(2, 3)} />);
    expect(screen.getByText(/Practice run ·/)).toBeInTheDocument();
    unmount();

    const sprint = WEEKEND_SESSIONS_2026.sprintWeekend.sessions.find((s) => s.kind === "race");
    if (sprint?.kind !== "race") throw new Error("fixture changed");
    renderWithProviders(<RaceTable entries={sprint.entries} />);
    expect(screen.getByRole("columnheader", { name: "Grid" })).toBeInTheDocument();
    expect(screen.getAllByRole("row").length).toBe(sprint.entries.length + 1);
  });
});
