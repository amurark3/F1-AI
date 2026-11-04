import { screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { DIRECTORY_2026, OPENF1_DRIVERS_MEXICO_2026 } from "@/test/fixtures";
import { apiUrl, server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";

import { TeamName } from "./TeamName";

// The directory is read for the calendar year, so match any season.
const DIRECTORY_URL = apiUrl("/api/profiles/:year/directory");

/** Serves the captured directory and counts the requests for it. */
function serveDirectory(): { requests: () => number } {
  let count = 0;
  server.use(
    http.get(DIRECTORY_URL, () => {
      count += 1;
      return HttpResponse.json(DIRECTORY_2026);
    }),
  );
  return { requests: () => count };
}

/** A team as OpenF1 spells it on the Mexico City entry list. */
function openF1Team(code: string): string {
  const team = OPENF1_DRIVERS_MEXICO_2026.find((driver) => driver.name_acronym === code)?.team_name;
  if (!team) throw new Error(`no team for ${code} in the OpenF1 list`);
  return team;
}

describe("TeamName", () => {
  it("prints f1db's name for a feed's spelling once the directory lands", async () => {
    serveDirectory();
    renderWithProviders(
      <>
        <TeamName name={openF1Team("BEA")} className="text-rc-ink-2" />
        <TeamName name={openF1Team("VER")} />
      </>,
    );

    // The payload's own spelling stands in until then.
    expect(screen.getByText("Haas F1 Team")).toHaveClass("text-rc-ink-2");
    expect(await screen.findByText("Haas")).toBeInTheDocument();
    expect(screen.getByText("Red Bull")).toBeInTheDocument();
  });

  it("prints the full name the payload sends without reading the directory", () => {
    const directory = serveDirectory();
    renderWithProviders(<TeamName variant="full" name="Mercedes" fullName="Mercedes AMG F1" />);

    expect(screen.getByText("Mercedes AMG F1")).toBeInTheDocument();
    expect(directory.requests()).toBe(0);
  });

  it("reads the full name from this season's directory when the payload has none", async () => {
    serveDirectory();
    renderWithProviders(<TeamName variant="full" name="Red Bull" />);

    expect(await screen.findByText("Red Bull Racing")).toBeInTheDocument();
  });

  it("leaves another season's team as the payload spells it", async () => {
    const directory = serveDirectory();
    renderWithProviders(<TeamName name="Haas F1 Team" year={2023} />);

    expect(screen.getByText("Haas F1 Team")).toBeInTheDocument();
    await screen.findByText("Haas F1 Team");
    expect(directory.requests()).toBe(0);
  });
});
