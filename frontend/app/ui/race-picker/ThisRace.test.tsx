import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { describe, expect, it, vi } from "vitest";

import { RACE_RESULTS_2026 } from "@/test/fixtures";
import { apiUrl, server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";

import { ThisRace } from "./ThisRace";

const race = { round: 19, name: "Mexico City Grand Prix", location: "Mexico City", status: "completed" };
const resultUrl = "/api/race-control/results/2025/19";
const nav = () => within(screen.getByRole("navigation", { name: "This race" }));

describe("ThisRace", () => {
  it("links the four views with the round and season when a race classification is published", async () => {
    server.use(http.get(apiUrl(resultUrl), () => HttpResponse.json(RACE_RESULTS_2026.mexicoCity)));

    renderWithProviders(<ThisRace race={{ ...race, status: "in_progress" }} year={2025} view="debrief" />);

    const debrief = await nav().findByRole("link", { name: "Debrief" });
    expect(debrief).toHaveAttribute("aria-current", "page");
    expect(
      nav()
        .getAllByRole("link")
        .map((link) => link.getAttribute("href")),
    ).toEqual([
      "/race-control/grand-prix?round=19&year=2025",
      "/race-control/telemetry?round=19&year=2025",
      "/race-control/debriefs?round=19&year=2025",
      "/race-control/rewind?round=19&year=2025",
    ]);
  });

  it("leaves post-race views unavailable when the schedule says completed but only a sprint has results", async () => {
    const request = vi.fn(() => HttpResponse.json({ ...RACE_RESULTS_2026.sprintWeekend, race: null }));
    server.use(http.get(apiUrl(resultUrl), request));

    renderWithProviders(<ThisRace race={race} year={2025} view="grand-prix" />);

    await vi.waitFor(() => expect(request).toHaveBeenCalledOnce());
    expect(
      nav()
        .getAllByRole("link")
        .map((link) => link.textContent),
    ).toEqual(["Grand Prix", "Telemetry"]);
    const locked = nav().getAllByRole("button");
    expect(locked.map((button) => button.textContent)).toEqual(["Debrief", "Rewind"]);
    for (const button of locked) expect(button).toHaveAttribute("aria-disabled", "true");
    await userEvent.hover(locked[0]);
    expect(locked[0]).toHaveAccessibleDescription("Unlocks once the race classification is published.");
    expect(nav().queryByText("after the race")).not.toBeInTheDocument();
  });

  it("leaves upcoming rounds open in Grand Prix and Telemetry without reading results", () => {
    const request = vi.fn(() => HttpResponse.json(RACE_RESULTS_2026.mexicoCity));
    server.use(http.get(apiUrl(resultUrl), request));

    renderWithProviders(<ThisRace race={{ ...race, status: "upcoming" }} year={2025} view="telemetry" />);

    expect(nav().getByRole("link", { name: "Telemetry" })).toHaveAttribute("aria-current", "page");
    expect(nav().queryByRole("link", { name: "Rewind" })).toBeNull();
    expect(request).not.toHaveBeenCalled();
  });
});
