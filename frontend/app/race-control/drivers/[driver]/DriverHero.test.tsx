import { screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it } from "vitest";

import { CLINCH_2026, DIRECTORY_2026, PROFILE_PAGES_2026 } from "@/test/fixtures";
import { apiUrl, server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";

import { DriverHero } from "./DriverHero";

const { hamilton, lawson, verstappen } = PROFILE_PAGES_2026;

beforeEach(() => {
  server.use(
    http.get(apiUrl("/api/profiles/:year/directory"), () => HttpResponse.json(DIRECTORY_2026 as never)),
    http.get(apiUrl("/api/race-control/standings/:year/clinch"), () =>
      HttpResponse.json(CLINCH_2026.afterRound20 as never),
    ),
  );
});

describe("DriverHero", () => {
  it("names the driver, the car, the team and where he stands", () => {
    renderWithProviders(<DriverHero profile={verstappen} />);

    expect(screen.getByRole("heading", { level: 1, name: "Max Verstappen" })).toBeInTheDocument();
    expect(screen.getByText("Car 3")).toHaveClass("sr-only");
    expect(screen.getByText("3", { selector: "b[aria-hidden='true']" })).toHaveStyle({ color: "#3671C6" });
    expect(screen.getByText(/Netherlands/)).toBeInTheDocument();
    expect(screen.getByText("P2 in the championship · 279 points · 111 behind Antonelli")).toBeInTheDocument();
    expect(screen.queryByText(/Also drove for/)).not.toBeInTheDocument();
  });

  it("shows the last five races beside the name", () => {
    renderWithProviders(<DriverHero profile={hamilton} />);

    expect(screen.getByText("Last five")).toBeInTheDocument();
    expect(screen.getAllByRole("listitem")).toHaveLength(5);
  });

  it("lists an earlier team with its rounds", () => {
    renderWithProviders(<DriverHero profile={lawson} />);

    expect(screen.getByText(/Also drove for/)).toHaveTextContent("Also drove for Red Bull (R12–14)");
  });

  it("leaves out the number, the nationality and the form when the data has none", () => {
    const bare = {
      ...hamilton,
      driver: { ...hamilton.driver, number: null, nationality: null },
      rounds: hamilton.rounds.map((round) => ({ ...round, race: null })),
    };
    renderWithProviders(<DriverHero profile={bare} />);

    expect(screen.queryByText(/^Car /)).not.toBeInTheDocument();
    expect(screen.queryByText("Last five")).not.toBeInTheDocument();
    expect(screen.queryByText(/United Kingdom/)).not.toBeInTheDocument();
  });
});
