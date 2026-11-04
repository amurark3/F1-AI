import { renderHook, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { SWRConfig } from "swr";
import { describe, expect, it } from "vitest";

import { CHAMPION_STATS, DIRECTORY_2026, OPENF1_DRIVERS_MEXICO_2026 } from "@/test/fixtures";
import { apiUrl, server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";

import { DriverLink, TeamLink, directorySeason, useSeasonDirectory } from "./EntityLinks";

import type { ReactNode } from "react";

/** Serves the captured directory for the calendar year and counts the requests for it. */
function serveDirectory(): { requests: () => number } {
  let count = 0;
  server.use(
    http.get(apiUrl(`/api/profiles/${directorySeason()}/directory`), () => {
      count += 1;
      return HttpResponse.json(DIRECTORY_2026);
    }),
  );
  return { requests: () => count };
}

function freshCache({ children }: { children: ReactNode }) {
  return <SWRConfig value={{ provider: () => new Map(), dedupingInterval: 0 }}>{children}</SWRConfig>;
}

describe("useSeasonDirectory", () => {
  it("reads the calendar year's directory once for every caller", async () => {
    const directory = serveDirectory();
    const { result } = renderHook(
      () => {
        useSeasonDirectory();
        return useSeasonDirectory();
      },
      { wrapper: freshCache },
    );

    await waitFor(() => expect(result.current?.drivers).toHaveLength(24));
    expect(directorySeason()).toBe(new Date().getFullYear());
    expect(directory.requests()).toBe(1);
  });

  it("reads nothing when the caller has what it needs", () => {
    const directory = serveDirectory();
    const { result } = renderHook(() => useSeasonDirectory(false), { wrapper: freshCache });

    expect(result.current).toBeUndefined();
    expect(directory.requests()).toBe(0);
  });
});

describe("DriverLink", () => {
  it("links a driver of this season to their page, by the feed's code or name", async () => {
    serveDirectory();
    const hirakawa = OPENF1_DRIVERS_MEXICO_2026.find((driver) => driver.name_acronym === "HIR");
    renderWithProviders(
      <>
        <DriverLink code={hirakawa?.name_acronym} name={hirakawa?.full_name} className="font-bold">
          Hirakawa
        </DriverLink>
        <DriverLink name="Nico HULKENBERG">Hülkenberg</DriverLink>
      </>,
    );

    const link = await screen.findByRole("link", { name: "Hirakawa" });
    expect(link).toHaveAttribute("href", "/race-control/drivers/ryo-hirakawa");
    expect(link).toHaveClass("font-bold");
    expect(screen.getByRole("link", { name: "Hülkenberg" })).toHaveAttribute(
      "href",
      "/race-control/drivers/nico-hulkenberg",
    );
  });

  it("leaves a driver who did not race this season as plain text", async () => {
    const directory = serveDirectory();
    const fangio = CHAMPION_STATS.most_driver_titles?.[2];
    renderWithProviders(
      <DriverLink name={fangio?.name} className="text-rc-ink-2">
        Fangio
      </DriverLink>,
    );

    await waitFor(() => expect(directory.requests()).toBe(1));
    expect(screen.getByText("Fangio")).toHaveClass("text-rc-ink-2");
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });
});

describe("TeamLink", () => {
  it("links a feed's spelling of a team on this season's grid", async () => {
    serveDirectory();
    renderWithProviders(<TeamLink name="Haas F1 Team">Haas</TeamLink>);

    expect(await screen.findByRole("link", { name: "Haas" })).toHaveAttribute(
      "href",
      "/race-control/constructors/haas",
    );
  });

  it("leaves a team off this season's grid as plain text, and links one by its f1db id", async () => {
    const directory = serveDirectory();
    renderWithProviders(
      <>
        <TeamLink name="Lotus" className="text-rc-ink-3">
          Lotus
        </TeamLink>
        <TeamLink id="williams">Williams</TeamLink>
      </>,
    );

    await waitFor(() => expect(directory.requests()).toBe(1));
    expect(screen.getByText("Lotus")).toHaveClass("text-rc-ink-3");
    expect(await screen.findByRole("link", { name: "Williams" })).toHaveAttribute(
      "href",
      "/race-control/constructors/williams",
    );
  });
});
