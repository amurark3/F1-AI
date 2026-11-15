import { screen, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useServerStatus, type ServerState } from "@/app/hooks/useServerStatus";
import { DIRECTORY_2026, RACE_RESULTS_2026 } from "@/test/fixtures";
import { apiUrl, server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";

import { ResultsTab } from "./ResultsTab";

import type { RaceResultsResponse } from "./resultsModel";

vi.mock("@/app/hooks/useServerStatus", () => ({ useServerStatus: vi.fn() }));

const RESULTS_URL = apiUrl("/api/race-control/results/2026/:round");

function answer(body: unknown): void {
  server.use(http.get(RESULTS_URL, () => HttpResponse.json(body as Record<string, unknown>)));
}

describe("ResultsTab", () => {
  beforeEach(() => {
    vi.mocked(useServerStatus).mockReturnValue({ status: "ready" } as ServerState);
    server.use(http.get(apiUrl("/api/profiles/:year/directory"), () => HttpResponse.json(DIRECTORY_2026)));
  });

  it("shows a skeleton, then Mexico City's final classification with its side panels", async () => {
    answer(RACE_RESULTS_2026.mexicoCity);
    renderWithProviders(<ResultsTab year={2026} round={19} />);

    expect(document.querySelector("[aria-busy='true']")).toBeInTheDocument();
    const heading = await screen.findByRole("heading", { name: "Max Verstappen wins; 5 cars retire" });
    expect(heading).toBeInTheDocument();
    expect(screen.getByText("Final")).toBeInTheDocument();
    expect(screen.getByText(/f1db v2026\.20\.0, mirroring the FIA final classification · final/)).toBeInTheDocument();
    expect(screen.getByText("71 laps ·", { exact: false })).toBeInTheDocument();
    expect(screen.getByText("Changed after the flag")).toBeInTheDocument();
    expect(screen.getByText("1:19.268")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Read the debrief" })).toBeInTheDocument();
    // Mexico had no sprint, so there is no switch.
    expect(screen.queryByRole("radiogroup", { name: "Classification" })).not.toBeInTheDocument();
  });

  it("switches between the sprint and the Grand Prix on a sprint weekend", async () => {
    answer(RACE_RESULTS_2026.sprintWeekend);
    const { user } = renderWithProviders(<ResultsTab year={2026} round={2} />);

    const group = await screen.findByRole("radiogroup", { name: "Classification" });
    expect(screen.getByText("Race classification")).toBeInTheDocument();

    await user.click(within(group).getByRole("radio", { name: "Sprint" }));
    expect(screen.getByText("Sprint classification")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /^George Russell wins/ })).toBeInTheDocument();
    // The sprint has no fastest-lap fact of its own.
    expect(screen.queryByText("Fastest lap", { selector: "p" })).not.toBeInTheDocument();

    await user.click(within(group).getByRole("radio", { name: "Grand Prix" }));
    expect(screen.getByText("Race classification")).toBeInTheDocument();
  });

  it("tags a classification provisional, with a laps count of zero when no laps are given", async () => {
    const race = RACE_RESULTS_2026.mexicoCity.race;
    const provisional: RaceResultsResponse = {
      ...RACE_RESULTS_2026.mexicoCity,
      race: race && {
        ...race,
        final: false,
        classification: race.classification.map((row) => ({ ...row, laps: null })),
        sources: [{ source: "openf1-session-result", role: "classification" }],
      },
    };
    answer(provisional);
    renderWithProviders(<ResultsTab year={2026} round={19} />);

    const tag = await screen.findByText("Provisional");
    expect(tag).toHaveClass("text-rc-blue");
    expect(screen.getByText(/OpenF1 session result · provisional until the FIA/)).toBeInTheDocument();
  });

  it("says so when the round has no classification yet", async () => {
    answer({ year: 2026, round: 20, race: null, sprint: null });
    renderWithProviders(<ResultsTab year={2026} round={20} />);

    expect(await screen.findByText("No classification has been published for this race yet.")).toBeInTheDocument();
  });

  it("owns its failure: the backend's handled error shows with a way to retry", async () => {
    answer({ year: 2026, round: 19, race: null, sprint: null, error: "Something went wrong. Try again shortly." });
    renderWithProviders(<ResultsTab year={2026} round={19} />);

    expect(await screen.findByText("Race results unavailable")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });
});
