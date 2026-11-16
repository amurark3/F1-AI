import { screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { PROFILE_PAGES_2026 } from "@/test/fixtures";
import { renderWithProviders } from "@/test/render";

import { TeamCard } from "./TeamCard";

import type { TeamsIndexTeam } from "../profiles/profilesModel";

const { teams } = PROFILE_PAGES_2026.teams_index;

function team(id: string): TeamsIndexTeam {
  const found = teams.find((item) => item.id === id);
  if (!found) throw new Error(`no ${id} in the fixture`);
  return found;
}

function renderCard(id: string) {
  return renderWithProviders(<TeamCard team={team(id)} leader={teams[0]} year={2026} through={20} index={0} />);
}

describe("TeamCard", () => {
  it("links to the team page and states the place, points and gap", () => {
    renderCard("red-bull");

    expect(screen.getByRole("link")).toHaveAttribute("href", "/race-control/constructors/red-bull");
    expect(screen.getByRole("heading", { name: "Red Bull" })).toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument();
    expect(screen.getByText("415 pts · −237")).toBeInTheDocument();
  });

  it("splits the points by what each driver scored for the team, and says which rounds a stand-in raced", () => {
    renderCard("red-bull");

    const bar = screen.getByRole("img", { name: "Points split: Verstappen 279, Hadjar 122, Lawson 14" });
    expect(within(bar).getAllByTitle(/pts$/)).toHaveLength(3);
    expect(screen.getByText("Max Verstappen")).toBeInTheDocument();
    expect(screen.getByText("279")).toBeInTheDocument();
    expect(screen.getByText("R12–14")).toBeInTheDocument();
    expect(screen.getByText("14")).toBeInTheDocument();
    expect(screen.getByText("R1–11, R15–20")).toBeInTheDocument();
    expect(screen.getByText("Verstappen scored 67% of the points")).toBeInTheDocument();
  });

  it("lists a driver with no points, with the round they raced, but gives them no segment", () => {
    renderCard("haas");

    expect(screen.getByText("Rafael Câmara")).toBeInTheDocument();
    expect(screen.getByText("R20")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Points split: Bearman 23, Ocon 7, Hirakawa 1" })).toBeInTheDocument();
    expect(screen.queryByTitle("Rafael Câmara · 0 pts")).not.toBeInTheDocument();
    expect(screen.getByText("Bearman scored 74% of the points")).toBeInTheDocument();
  });

  it("marks the leader", () => {
    renderCard("mercedes");
    expect(screen.getByText("652 pts · Leader")).toBeInTheDocument();
  });
});

describe("TeamCard without points", () => {
  it("shows no share bar role and says so", () => {
    renderCard("cadillac");

    expect(screen.queryByRole("img")).not.toBeInTheDocument();
    expect(screen.getByText("No points yet")).toBeInTheDocument();
  });

  it("shows a dash for an unranked team", () => {
    renderWithProviders(
      <TeamCard team={{ ...team("cadillac"), position: null }} leader={teams[0]} year={2026} through={20} index={0} />,
    );

    expect(screen.getByText("—")).toBeInTheDocument();
    expect(screen.getByText("0 pts · Unranked")).toBeInTheDocument();
  });
});
