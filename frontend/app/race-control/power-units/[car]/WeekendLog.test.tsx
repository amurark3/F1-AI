import { screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useServerStatus, type ServerState } from "@/app/hooks/useServerStatus";
import { POWER_UNITS_2026 } from "@/test/fixtures";
import { renderCar } from "@/test/renderCar";

import { WeekendLog } from "./WeekendLog";

vi.mock("@/app/hooks/useServerStatus", () => ({ useServerStatus: vi.fn() }));

beforeEach(() => {
  vi.mocked(useServerStatus).mockReturnValue({ status: "ready" } as ServerState);
});

function weekend(round: number): HTMLElement {
  return document.getElementById(`round-${round}`)!;
}

describe("WeekendLog for car 6", () => {
  it("lists the weekends with new units, newest first", async () => {
    await renderCar(WeekendLog, POWER_UNITS_2026);

    expect(screen.getByText("10 weekends with new units · newest first")).toBeInTheDocument();
    const ids = [...document.querySelectorAll("article")].map((article) => article.id);
    expect(ids).toEqual([
      "round-17",
      "round-16",
      "round-13",
      "round-12",
      "round-10",
      "round-8",
      "round-5",
      "round-4",
      "round-2",
      "round-1",
    ]);
  });

  it("R17: the pit-lane start that made a drop redundant, with the stewards' document", async () => {
    await renderCar(WeekendLog, POWER_UNITS_2026);

    const article = within(weekend(17));
    expect(article.getByRole("heading", { level: 3, name: "Singapore GP" })).toBeInTheDocument();
    expect(article.getByText("11 Oct")).toBeInTheDocument();
    expect(article.getByText("Stewards decided")).toBeInTheDocument();
    expect(article.getByText("Pit-lane start")).toBeInTheDocument();
    expect(article.getByText("ICE #8 · TC #7 · EXH #7 · PU-ANC #8 · first used in Qualifying")).toBeInTheDocument();
    expect(
      article.getByText("The units alone carried 5 grid places; the pit-lane start made that drop redundant."),
    ).toBeInTheDocument();
    const doc = article.getByRole("link", { name: /^Stewards · Doc 83 · Infringement · Car 6/ });
    expect(doc).toHaveAttribute("target", "_blank");
    expect(doc).toHaveAttribute("rel", "noopener noreferrer");
    expect(doc).toHaveTextContent("(opens the FIA document)");
    expect(article.getByText("Started from the pit lane")).toBeInTheDocument();
    expect(article.queryByText("FIA reports")).not.toBeInTheDocument();
    expect(article.queryByText("Stand-in")).not.toBeInTheDocument();
  });

  it("R13: the stand-in note, the chips in two rows, and the TD report", async () => {
    await renderCar(WeekendLog, POWER_UNITS_2026);

    const article = within(weekend(13));
    expect(article.getByText("Stand-in")).toBeInTheDocument();
    expect(article.getByText("Stand-in").closest("p")).toHaveTextContent(
      "Liam Lawson drove car 6 this weekend under his own number, #30. Units fitted to this car count against its allocation, the one Hadjar races with, whoever drives it (Article B8.2.7).",
    );
    expect(article.getByText("Beyond the allocation")).toBeInTheDocument();
    expect(article.getByText("Within")).toBeInTheDocument();
    expect(article.getByText("Qualified P14 → started from the pit lane")).toBeInTheDocument();
    expect(article.getByRole("link", { name: /^TD report · Doc 33 ↗/ })).toBeInTheDocument();
  });

  it("R10: the grid, and no stand-in note for the regular driver", async () => {
    await renderCar(WeekendLog, POWER_UNITS_2026);

    expect(within(weekend(10)).getByText("Qualified P10 → started P21")).toBeInTheDocument();
    expect(within(weekend(10)).queryByText("Stand-in")).not.toBeInTheDocument();
  });
});

describe("WeekendLog states", () => {
  it("car 30, R19: a ruling not found gets its tag, its gap note and its grid", async () => {
    await renderCar(WeekendLog, POWER_UNITS_2026, { segment: "30" });

    const article = within(weekend(19));
    expect(article.getByText("No ruling found")).toBeInTheDocument();
    expect(
      article.getByText(/no stewards' decision naming them was found in the collected documents\./),
    ).toBeInTheDocument();
    expect(article.getByText("Started from the pit lane")).toBeInTheDocument();
    expect(article.getByRole("link", { name: /^TD report · Doc 14/ })).toBeInTheDocument();
  });

  it("a pending weekend is tagged and noted", async () => {
    const changed = structuredClone(POWER_UNITS_2026);
    const event = changed.cars.find((c) => c.car_number === 30)!.events.find((e) => e.round === 19)!;
    event.penalty_status = "pending";
    await renderCar(WeekendLog, changed, { segment: "30" });

    expect(within(weekend(19)).getByText("Ruling pending")).toBeInTheDocument();
    expect(within(weekend(19)).getByText(/the stewards have not published a decision yet\./)).toBeInTheDocument();
  });

  it("a car with three drivers: the regular driver's weekend has no stand-in note", async () => {
    await renderCar(WeekendLog, POWER_UNITS_2026, { segment: "51" });

    expect(within(weekend(13)).queryByText("Stand-in")).not.toBeInTheDocument();
  });

  it("a stand-in in the car's own number, a unit no longer counted, a document with no number, and an unnamed round", async () => {
    const changed = structuredClone(POWER_UNITS_2026);
    const six = changed.cars.find((c) => c.car_number === 6)!;
    const event = six.events.find((e) => e.round === 13)!;
    event.driver!.car_number = 6;
    event.new_parts[0].not_counted_from = 15;
    event.sources[0].number = null;
    event.decisions[0].nominal_places = null;
    changed.rounds = (changed.rounds ?? []).filter((r) => r.round !== 13);
    await renderCar(WeekendLog, changed);

    const article = within(weekend(13));
    expect(article.getByText(/drove car 6 this weekend\./)).toBeInTheDocument();
    expect(article.getByRole("link", { name: /^TD report ↗/ })).toBeInTheDocument();
    expect(article.getByRole("heading", { level: 3, name: "Round 13" })).toBeInTheDocument();
  });

  it("says so when a car has no new units yet", async () => {
    const changed = structuredClone(POWER_UNITS_2026);
    changed.cars.find((c) => c.car_number === 12)!.events = [];
    await renderCar(WeekendLog, changed, { segment: "12" });

    expect(screen.getByText("No new units recorded for this car yet.")).toBeInTheDocument();
    expect(screen.queryByText(/newest first/)).not.toBeInTheDocument();
  });

  it("renders nothing for an unknown car or an uncollected season", async () => {
    const unknown = await renderCar(WeekendLog, POWER_UNITS_2026, { segment: "99" });
    expect(unknown.container).toBeEmptyDOMElement();
    unknown.unmount();

    const none = await renderCar(WeekendLog, { ...POWER_UNITS_2026, available: false, cars: [] });
    expect(none.container).toBeEmptyDOMElement();
  });

  it("keeps its head over a failure card for an error payload", async () => {
    await renderCar(WeekendLog, { error: "boom" });

    expect(await screen.findByText("Weekend log unavailable")).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 2, name: "Weekend by weekend" })).toBeInTheDocument();
  });
});
