import { screen, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it } from "vitest";

import { DIRECTORY_2026, GRIDS_2026, PREDICTION_REVIEW_R19 } from "@/test/fixtures";
import { apiUrl, server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";

import { OrderTable, orderTitle } from "./OrderTable";

import type { PredictionPhase } from "./predictionModel";

const ROWS = PREDICTION_REVIEW_R19.predictions;

function show(phase: PredictionPhase, predictions = ROWS, grid = GRIDS_2026.mexicoCityOfficial) {
  return renderWithProviders(
    <OrderTable
      predictions={predictions}
      driverLookup={{}}
      phase={phase}
      grid={grid}
      gridLoading={false}
      data={PREDICTION_REVIEW_R19}
    />,
  );
}

describe("OrderTable (Mexico City, the stored post-qualifying call)", () => {
  beforeEach(() => {
    server.use(http.get(apiUrl("/api/profiles/:year/directory"), () => HttpResponse.json(DIRECTORY_2026)));
  });

  it("has the four columns of the design and none of the removed ones", () => {
    show("post_qualifying");

    const head = screen.getAllByRole("columnheader").map((cell) => cell.textContent);
    expect(head).toEqual(["P", "Driver", "Agreement band", "Agreement", "vs grid"]);
    for (const removed of ["Team", "Pts", "Win est.", "Podium est.", "Crash%", "DNF%"]) {
      expect(screen.queryByRole("columnheader", { name: removed })).not.toBeInTheDocument();
    }
  });

  it("prints the agreement as a band with no % sign, and says it is not a probability", () => {
    show("post_qualifying");

    const first = screen.getAllByRole("row")[1];
    expect(within(first).getByText("74–89")).toBeInTheDocument();
    expect(first).not.toHaveTextContent("%");
    expect(screen.getByText(/a score, not a chance of finishing there/)).toBeInTheDocument();
  });

  it("titles the table from the order and counts the cars", () => {
    show("post_qualifying");

    expect(screen.getByRole("heading", { name: orderTitle(ROWS, {}) })).toBeVisible();
    expect(screen.getByText("Predicted order · 22 cars")).toBeInTheDocument();
    expect(screen.getByText("P1")).toHaveClass("text-rc-gold");
  });

  it("reads each car against the starting grid after qualifying, and the pit-lane starter as from pit lane", () => {
    show("post_qualifying");

    const lawson = screen.getByText("LAW").closest("tr")!;
    expect(within(lawson).getByText("from pit lane")).toBeInTheDocument();
    expect(lawson).not.toHaveTextContent(/P22/);
    expect(screen.getByText(/vs grid: official grid sheet/)).toBeInTheDocument();
  });

  it("hides vs grid before qualifying and says it joins later", () => {
    show("pre_qualifying");

    expect(screen.queryByRole("columnheader", { name: "vs grid" })).not.toBeInTheDocument();
    expect(screen.getByText(/vs grid joins after qualifying/)).toBeInTheDocument();
    expect(screen.getByText(/^Pre-qualifying projection/)).toBeInTheDocument();
  });

  it("marks a stand-in's seat as TBC with the reason on hover", () => {
    const rows = ROWS.map((row, index) =>
      index === 3 ? { ...row, seat_tbc: true, seat_tbc_reason: "Hirakawa raced in place of Ocon" } : row,
    );
    show("post_qualifying", rows);

    const tag = screen.getByText("Seat TBC");
    expect(tag.parentElement).toHaveAttribute("title", "Hirakawa raced in place of Ocon");
  });

  it("marks a stand-in's seat as TBC even with no reason given", () => {
    show("post_qualifying", [{ ...ROWS[0], seat_tbc: true }, ...ROWS.slice(1)]);

    expect(screen.getByText("Seat TBC").parentElement).not.toHaveAttribute("title");
  });

  it("titles a one-car order, and reads without sources when the payload names none", () => {
    expect(orderTitle([ROWS[0]], {})).toMatch(/is called to win$/);
    renderWithProviders(<OrderTable predictions={ROWS} driverLookup={{}} phase="pre_qualifying" gridLoading />);
    expect(screen.getByText("Pre-qualifying projection")).toBeInTheDocument();
  });
});
