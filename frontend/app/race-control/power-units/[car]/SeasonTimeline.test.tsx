import { screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useServerStatus, type ServerState } from "@/app/hooks/useServerStatus";
import { POWER_UNITS_2026 } from "@/test/fixtures";
import { renderCar } from "@/test/renderCar";

import { SeasonTimeline } from "./SeasonTimeline";

vi.mock("@/app/hooks/useServerStatus", () => ({ useServerStatus: vi.fn() }));

beforeEach(() => {
  vi.mocked(useServerStatus).mockReturnValue({ status: "ready" } as ServerState);
});

describe("SeasonTimeline for car 6", () => {
  it("titles the season and counts the weekends, naming the stand-in", async () => {
    await renderCar(SeasonTimeline, POWER_UNITS_2026);

    expect(screen.getByRole("heading", { level: 2, name: "Season" })).toBeInTheDocument();
    expect(
      screen.getByRole("heading", {
        level: 3,
        name: "Five rulings in 20 rounds: three grid drops and two pit-lane starts",
      }),
    ).toBeInTheDocument();
    expect(screen.getByText(/^New units fitted at 10 of 20/).closest("p")).toHaveTextContent(
      "New units fitted at 10 of 20 Grand Prix weekends · Lawson (#30) stood in at R12–R14",
    );
  });

  it("makes one cell per Grand Prix, linking the weekends that have a log entry", async () => {
    await renderCar(SeasonTimeline, POWER_UNITS_2026);

    const cells = screen.getAllByRole("listitem").filter((item) => item.closest("ol"));
    expect(cells).toHaveLength(23);
    expect(screen.getByRole("link", { name: "Belgian GP: 30 grid places" })).toHaveAttribute("href", "#round-10");
    expect(screen.getByTitle("Japanese GP: nothing new").tagName).toBe("SPAN");
    expect(screen.getByLabelText("Japanese GP: nothing new")).toHaveTextContent("·");
    expect(screen.getByTitle("Las Vegas GP: no FIA documents yet")).toBeInTheDocument();
  });

  it("marks the stand-in's weekends in his own code", async () => {
    await renderCar(SeasonTimeline, POWER_UNITS_2026);

    const italian = screen.getByRole("link", { name: "Italian GP: 35 grid places" });
    expect(italian).toHaveTextContent("LAW");
    expect(screen.getByRole("link", { name: "Australian GP: 7 new units" })).toHaveTextContent("HAD");
  });

  it("explains each mark, and the stand-in", async () => {
    await renderCar(SeasonTimeline, POWER_UNITS_2026);

    const legend = screen.getByRole("list", { name: "Legend" });
    expect(legend).toHaveTextContent("new units");
    expect(legend).toHaveTextContent("no FIA documents yet");
    expect(legend).toHaveTextContent("LAWstand-in driver");
    expect(legend).not.toHaveTextContent("round not pinned down");
  });
});

describe("SeasonTimeline states", () => {
  it("car 12 has one driver, so no driver row and no stand-in key", async () => {
    await renderCar(SeasonTimeline, POWER_UNITS_2026, { segment: "12" });

    expect(screen.queryByText("stand-in driver")).not.toBeInTheDocument();
    expect(screen.queryByText("HAD")).not.toBeInTheDocument();
  });

  it("car 18 shows the units whose round is not pinned down, and says so in the key", async () => {
    await renderCar(SeasonTimeline, POWER_UNITS_2026, { segment: "18" });

    expect(
      screen.getByText(
        "New units fitted at 12 of 20 Grand Prix weekends · 5 units arrived between R18 and R19, round not pinned down",
      ),
    ).toBeInTheDocument();
    expect(screen.getByLabelText(/^United States GP: 5 new units arrived at this round or another/)).toHaveTextContent(
      "5",
    );
    expect(screen.getByRole("list", { name: "Legend" })).toHaveTextContent("round not pinned down");
  });

  it("car 30 marks a ruling not found", async () => {
    await renderCar(SeasonTimeline, POWER_UNITS_2026, { segment: "30" });

    expect(screen.getByRole("link", { name: "Mexican GP: no stewards' decision found" })).toHaveTextContent("!");
  });

  it("copes with no latest round", async () => {
    await renderCar(SeasonTimeline, { ...POWER_UNITS_2026, as_of: null });

    expect(screen.getByText(/^New units fitted at 10 Grand Prix weekends/)).toBeInTheDocument();
  });

  it("renders nothing for an unknown car or an uncollected season", async () => {
    const unknown = await renderCar(SeasonTimeline, POWER_UNITS_2026, { segment: "99" });
    expect(unknown.container).toBeEmptyDOMElement();
    unknown.unmount();

    const none = await renderCar(SeasonTimeline, { ...POWER_UNITS_2026, available: false, cars: [] });
    expect(none.container).toBeEmptyDOMElement();
  });

  it("keeps its head over a failure card for an error payload", async () => {
    await renderCar(SeasonTimeline, { error: "boom" });

    expect(await screen.findByText("Season unavailable")).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 2, name: "Season" })).toBeInTheDocument();
  });
});
