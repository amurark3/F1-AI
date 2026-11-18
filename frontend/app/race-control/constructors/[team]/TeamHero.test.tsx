import { screen, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it } from "vitest";

import { DIRECTORY_2026, PROFILE_PAGES_2026 } from "@/test/fixtures";
import { apiUrl, server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";

import { TeamHero } from "./TeamHero";

const { mercedes, red_bull: redBull } = PROFILE_PAGES_2026;

beforeEach(() => {
  server.use(http.get(apiUrl("/api/profiles/:year/directory"), () => HttpResponse.json(DIRECTORY_2026 as never)));
});

describe("TeamHero", () => {
  it("names the team, its full name and power unit, and where it stands", () => {
    renderWithProviders(<TeamHero profile={mercedes} />);

    expect(screen.getByRole("heading", { level: 1, name: "Mercedes" })).toBeInTheDocument();
    expect(screen.getByText("Constructors' championship · 2026")).toBeInTheDocument();
    expect(screen.getByText("Mercedes AMG F1 · Mercedes power unit")).toBeInTheDocument();
    expect(screen.getByText("P1")).toBeInTheDocument();
    expect(screen.getByText("652 points, 142 clear of Ferrari with 3 rounds to run.")).toBeInTheDocument();
  });

  it("gives just the full name when f1db names no power unit, and a dash for no place", () => {
    const bare = {
      ...mercedes,
      team: { ...mercedes.team, power_unit: null, position: null },
    };
    renderWithProviders(<TeamHero profile={bare} />);

    expect(screen.getByText("Mercedes AMG F1")).toBeInTheDocument();
    expect(screen.getByText("—")).toBeInTheDocument();
  });

  it("renders the clinch slot right after the standing sentence, only when given", () => {
    const { unmount } = renderWithProviders(<TeamHero profile={mercedes} />);
    expect(screen.queryByText("Can clinch in São Paulo.")).not.toBeInTheDocument();
    unmount();

    renderWithProviders(<TeamHero profile={mercedes} clinch={<em>Can clinch in São Paulo.</em>} />);
    const sentence = screen.getByText(/652 points/);
    expect(within(sentence).getByText("Can clinch in São Paulo.")).toBeInTheDocument();
  });

  it("lists the current line-up with each car's number, record and a link to the driver", () => {
    renderWithProviders(<TeamHero profile={mercedes} />);

    const kimi = screen.getByRole("link", { name: "Kimi Antonelli" });
    expect(kimi).toHaveAttribute("href", "/race-control/drivers/kimi-antonelli");
    expect(screen.getByText("Car 12")).toHaveClass("sr-only");
    expect(screen.getByText("12", { selector: "[aria-hidden='true']" })).toBeInTheDocument();
    expect(screen.getByText("390 pts · P1 · 9 wins · 7 poles")).toBeInTheDocument();
    expect(screen.getByText("Car 63")).toBeInTheDocument();
  });

  it("says one win and one pole in the singular, and a dash for a car with no number or place", () => {
    const [ant, rus] = mercedes.drivers;
    const drivers = [{ ...ant, number: null, position: null }, rus];
    const race = { ...mercedes.rounds[0].results[0].race!, position: 1, status: "finished" as const, pole: true };
    const rounds = [{ ...mercedes.rounds[0], results: [{ driver_id: ant.id, race, sprint: null }] }];
    renderWithProviders(<TeamHero profile={{ ...mercedes, drivers, rounds }} />);

    expect(screen.getByText("390 pts · — · 1 win · 1 pole")).toBeInTheDocument();
    expect(screen.queryByText("Car 12")).not.toBeInTheDocument();
  });

  it("separates several stand-ins with commas", () => {
    const [first, second] = redBull.drivers;
    const extra = { ...second, id: "x-driver", name: "Ex Driver", last_name: "Driver", code: "XDR", current: false };
    const drivers = [first, { ...second, current: false }, extra];
    renderWithProviders(<TeamHero profile={{ ...redBull, drivers }} />);

    expect(screen.getByText(/Also raced/)).toHaveTextContent(/Hadjar.*HAD.*R1–11, R15–20, Driver.*XDR/);
  });

  it("lists anyone else who raced for the team with their rounds", () => {
    renderWithProviders(<TeamHero profile={redBull} />);

    expect(screen.getByText(/Also raced/)).toHaveTextContent(/Also raced:.*Lawson.*LAW.*R12–14/);
    expect(screen.getByRole("link", { name: /Lawson/ })).toHaveAttribute("href", "/race-control/drivers/liam-lawson");
    expect(screen.queryByRole("link", { name: /power units/i })).not.toBeInTheDocument();
  });
});
