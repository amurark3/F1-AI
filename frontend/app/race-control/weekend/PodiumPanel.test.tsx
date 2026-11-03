import { screen } from "@testing-library/react";
import { useReducedMotion } from "framer-motion";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { DIRECTORY_2026, SAO_PAULO_2026 } from "@/test/fixtures";
import { apiUrl, server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";

import { PodiumPanel } from "./PodiumPanel";

import type * as FramerMotion from "framer-motion";

vi.mock("framer-motion", async (importOriginal) => ({
  ...(await importOriginal<typeof FramerMotion>()),
  useReducedMotion: vi.fn(),
}));

// Entity links read the directory for the calendar year, so match any season.
const DIRECTORY_URL = apiUrl("/api/profiles/:year/directory");

describe("PodiumPanel", () => {
  beforeEach(() => {
    vi.mocked(useReducedMotion).mockReturnValue(true);
    server.use(http.get(DIRECTORY_URL, () => HttpResponse.json(DIRECTORY_2026)));
  });

  it("draws the model's São Paulo podium second, first, third, with each pick's mid confidence", async () => {
    renderWithProviders(<PodiumPanel podium={SAO_PAULO_2026.podium} />);

    expect(screen.getByRole("heading", { name: "Projected podium" })).toBeInTheDocument();
    const codes = screen.getAllByText(/^(ANT|VER|RUS)$/).map((code) => code.textContent);
    expect(codes).toEqual(["VER", "ANT", "RUS"]);
    // ANT 60–75 → 68, VER 56–71 → 64, RUS 48–63 → 56.
    expect(screen.getAllByText(/% conf\.$/).map((label) => label.textContent)).toEqual([
      "64% conf.",
      "68% conf.",
      "56% conf.",
    ]);
    expect(await screen.findByRole("link", { name: "Andrea Kimi Antonelli" })).toHaveAttribute(
      "href",
      "/race-control/drivers/kimi-antonelli",
    );
    expect(screen.getByRole("link", { name: "Red Bull" })).toHaveAttribute(
      "href",
      "/race-control/constructors/red-bull",
    );
  });

  it("waits for the race model before drawing a podium", () => {
    renderWithProviders(<PodiumPanel podium={[]} />);

    expect(screen.getByText("The podium appears once the race model has inputs for this weekend.")).toBeInTheDocument();
    expect(screen.queryByText(/% conf\.$/)).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Full predicted order" })).toHaveAttribute(
      "href",
      "/race-control/grand-prix",
    );
  });
});
