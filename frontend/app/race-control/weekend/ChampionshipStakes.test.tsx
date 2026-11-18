import { screen, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it } from "vitest";

import { DIRECTORY_2026, SAO_PAULO_2026, STAKES_2026 } from "@/test/fixtures";
import { apiUrl, server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";

import { ChampionshipStakes } from "./ChampionshipStakes";

// Entity links read the directory for the calendar year, so match any season.
const DIRECTORY_URL = apiUrl("/api/profiles/:year/directory");

const MARK_NOTE =
  " · dashed mark = the leader's total less the points left: a bar short of it can no longer catch the leader";

function rows(): string[] {
  return within(screen.getByRole("list"))
    .getAllByRole("listitem")
    .map((row) => row.textContent);
}

function footer(): string | null | undefined {
  return screen.queryByText(/to count/)?.textContent;
}

describe("ChampionshipStakes", () => {
  beforeEach(() => {
    server.use(http.get(DIRECTORY_URL, () => HttpResponse.json(DIRECTORY_2026)));
  });

  it("shows Antonelli's decided title after round 19, with everyone else out of reach", async () => {
    const { container } = renderWithProviders(<ChampionshipStakes stakes={SAO_PAULO_2026.stakes} venue="São Paulo" />);

    expect(screen.getByRole("heading", { name: "What's at stake" })).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: "Drivers" })).toBeChecked();
    expect(screen.getByText("Kimi Antonelli has already clinched the title.")).toHaveClass("border-rc-gold/35");
    expect(rows()).toEqual([
      "P1Kimi AntonelliANT380",
      "P2Max VerstappenVERout261−119",
      "P3Lewis HamiltonHAMout259−121",
      "P4George RussellRUSout250−130",
      "P5Charles LeclercLECout245−135",
      "P6Lando NorrisNORout221−159",
    ]);
    // Out of reach: each track carries a dashed mark at the leader's points minus the 100 left.
    const marks = container.querySelectorAll<HTMLElement>("li span[aria-hidden].border-dashed");
    expect(marks).toHaveLength(6);
    expect(marks[0].style.left).toMatch(/^73\.68/);
    expect(container.querySelector("[style*='gradient']")).toBeNull();
    expect(footer()).toBe(
      `Standings after round 19 · confirmed · 4 races · 0 sprints to count · 100 pts max${MARK_NOTE}`,
    );
    expect(await screen.findByRole("link", { name: /Antonelli/ })).toHaveAttribute(
      "href",
      "/race-control/drivers/kimi-antonelli",
    );
  });

  it("switches to the constructors, where Mercedes can clinch in São Paulo", async () => {
    const { user, container } = renderWithProviders(
      <ChampionshipStakes stakes={SAO_PAULO_2026.stakes} venue="São Paulo" />,
    );

    await user.click(screen.getByRole("radio", { name: "Teams" }));

    expect(screen.getByRole("radio", { name: "Teams" })).toBeChecked();
    expect(screen.getByRole("radio", { name: "Drivers" })).not.toBeChecked();
    expect(screen.getByText("Mercedes clinch in São Paulo if they outscore Ferrari by 3.")).toHaveClass(
      "border-rc-gold/35",
    );
    expect(container.querySelector(".motion-safe\\:animate-pulse")).not.toBeInTheDocument();
    expect(rows().slice(0, 3)).toEqual(["P1Mercedes630", "P2Ferrari504−126", "P3Red Bullout382−248"]);
    expect(footer()).toBe(
      `Standings after round 19 · confirmed · 4 races · 0 sprints to count · 172 pts max${MARK_NOTE}`,
    );
    expect(await screen.findByRole("link", { name: "Ferrari" })).toHaveAttribute(
      "href",
      "/race-control/constructors/ferrari",
    );
  });

  it("scales each bar to the leader's points", () => {
    renderWithProviders(<ChampionshipStakes stakes={SAO_PAULO_2026.stakes} venue="São Paulo" />);

    const bars = within(screen.getByRole("list"))
      .getAllByRole("listitem")
      .map((row) => (row.lastElementChild?.firstElementChild as HTMLElement | null)?.style.width);
    expect(bars[0]).toBe("100%");
    expect(bars[1]).toMatch(/^68\.68/);
  });

  it("says the title cannot be settled after round 1, with no one out yet", () => {
    renderWithProviders(<ChampionshipStakes stakes={STAKES_2026.afterRound1} venue="Shanghai" />);

    expect(screen.getByText("The title can't be settled in Shanghai — 598 pts still on offer.")).toBeInTheDocument();
    expect(document.querySelector("span.border-dashed")).toBeNull();
    expect(screen.getByText(/can't be settled/)).toHaveClass("border-rc-blue/35");
    expect(screen.queryByText("out")).not.toBeInTheDocument();
    expect(footer()).toBe("Standings after round 1 · confirmed · 22 races · 6 sprints to count · 598 pts max");
  });

  it("waits for the season's first result before the table has a round", () => {
    renderWithProviders(<ChampionshipStakes stakes={STAKES_2026.preseason} venue="Melbourne" />);

    expect(screen.getByText("Standings will appear once the season's first result is in.")).toBeInTheDocument();
    expect(screen.queryByRole("list")).not.toBeInTheDocument();
    expect(footer()).toBe("23 races · 6 sprints to count");
  });

  it("says nothing about points left when there are no stakes at all", () => {
    renderWithProviders(<ChampionshipStakes stakes={undefined} venue="São Paulo" />);

    expect(screen.getByText("Standings will appear once the season's first result is in.")).toBeInTheDocument();
    expect(footer()).toBeUndefined();
  });
});
