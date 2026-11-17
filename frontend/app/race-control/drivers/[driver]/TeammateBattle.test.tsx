import { screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it } from "vitest";

import { DIRECTORY_2026, PROFILE_PAGES_2026 } from "@/test/fixtures";
import { apiUrl, server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";

import { TeammateBattle } from "./TeammateBattle";

const { verstappen, hamilton } = PROFILE_PAGES_2026;

beforeEach(() => {
  server.use(http.get(apiUrl("/api/profiles/:year/directory"), () => HttpResponse.json(DIRECTORY_2026 as never)));
});

describe("TeammateBattle", () => {
  it("shows the race and grid counts with the counting rule on screen", () => {
    renderWithProviders(<TeammateBattle profile={verstappen} />);

    expect(screen.getByText(/^Teammate battle · vs/)).toHaveTextContent("Teammate battle · vs Isack Hadjar");
    expect(
      screen.getByRole("heading", { level: 3, name: "Verstappen finished ahead 14 times in 17" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Verstappen ahead at the flag")).toBeInTheDocument();
    expect(screen.getByText("Hadjar ahead")).toBeInTheDocument();
    expect(screen.getByText("Hadjar started ahead")).toBeInTheDocument();
    expect(screen.getByText("14")).toBeInTheDocument();
    expect(screen.getByText("12")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Finished ahead: Verstappen 14, Hadjar 3" })).toBeInTheDocument();
    expect(screen.getByText(/A retirement or disqualification counts as finishing behind/)).toHaveTextContent(
      "Not counted: R12–14 alongside Lawson.",
    );
  });

  it("keys the two colours by name", () => {
    renderWithProviders(<TeammateBattle profile={hamilton} />);

    expect(screen.getByRole("list", { name: "Legend" })).toHaveTextContent("HamiltonLeclerc");
  });

  it("says so when there is no teammate to compare with", () => {
    renderWithProviders(<TeammateBattle profile={{ ...hamilton, teammates: [] }} />);

    expect(screen.getByText("Teammate battle")).toBeInTheDocument();
    expect(screen.getByText("No race alongside a teammate yet.")).toBeInTheDocument();
  });
});
