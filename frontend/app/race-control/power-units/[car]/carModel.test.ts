import { describe, expect, it } from "vitest";

import { POWER_UNITS_2026 } from "@/test/fixtures";

import {
  roundsByNumber,
  type CarEvent,
  type Part,
  type PowerUnitCar,
  type PowerUnitsResponse,
} from "../powerUnitsModel";

import {
  allocationGroups,
  carKpis,
  carNotes,
  countWord,
  decisionLine,
  defaultPart,
  docLabel,
  engineFigure,
  gapNote,
  heroMeta,
  inspectorHead,
  isStandIn,
  ledgerRows,
  ledgerTitle,
  lineup,
  nominalNote,
  ordinal,
  rulingFor,
  seasonCells,
  sourceLine,
  timelineSub,
  timelineTitle,
  tileLabel,
  weekendsAside,
} from "./carModel";

const DATA = POWER_UNITS_2026;
const ROUNDS = roundsByNumber(DATA.rounds);

function car(number: number, data: PowerUnitsResponse = DATA): PowerUnitCar {
  const found = data.cars.find((item) => item.car_number === number);
  if (!found) throw new Error(`no car ${number}`);
  return found;
}

function part(item: PowerUnitCar, code: string, number: number): Part {
  const found = item.elements.find((usage) => usage.code === code)?.parts.find((entry) => entry.number === number);
  if (!found) throw new Error(`no part ${code} ${number}`);
  return found;
}

/** A hand-edited copy of one car; the fixture is never touched. */
function clone(number: number): PowerUnitCar {
  return structuredClone(car(number));
}

describe("words", () => {
  it("spells counts to ten and uses digits above", () => {
    expect(countWord(0)).toBe("no");
    expect(countWord(5, true)).toBe("Five");
    expect(countWord(11)).toBe("11");
  });

  it("makes ordinals, with the teens in th", () => {
    expect([1, 2, 3, 4, 11, 12, 13, 21, 22].map(ordinal)).toEqual([
      "1st",
      "2nd",
      "3rd",
      "4th",
      "11th",
      "12th",
      "13th",
      "21st",
      "22nd",
    ]);
  });
});

describe("isStandIn", () => {
  it("is the driver who is neither the regular nor the current one", () => {
    const six = car(6);
    expect(
      isStandIn(
        six,
        six.drivers.find((d) => d.code === "LAW")!,
      ),
    ).toBe(true);
    expect(isStandIn(six, six.driver)).toBe(false);
    expect(isStandIn(six, null)).toBe(false);
  });

  it("does not tag the regular driver of a car that changed hands, nor its new one", () => {
    const fifty1 = car(51);
    const codes = fifty1.drivers.map((stint) => [stint.code, isStandIn(fifty1, stint)]);
    expect(codes).toEqual([
      ["OCO", false],
      ["HIR", true],
      ["CAM", false],
    ]);
  });
});

describe("heroMeta and engineFigure", () => {
  it("adds the shared-seat sentence only for a car with several drivers", () => {
    expect(heroMeta(car(6))).toBe(
      "Every power-unit element fitted to car 6 this season, where it arrived and what it cost. Elements belong to the car, so the penalties follow the car, never the driver.",
    );
    expect(heroMeta(car(12))).toBe(
      "Every power-unit element fitted to car 12 this season, where it arrived and what it cost.",
    );
  });

  it("says the most of any car only for the unique maximum", () => {
    expect(engineFigure(car(6), DATA.cars)).toEqual({
      value: "8",
      unit: "engines",
      line: "fitted against an allocation of 4, the most of any car this season.",
    });
    expect(engineFigure(car(30), DATA.cars)).toEqual({
      value: "5",
      unit: "engines",
      line: "fitted against an allocation of 4.",
    });
  });

  it("handles a tie, a single engine, an unstated allocation and no engine row", () => {
    const tied = clone(30);
    tied.elements.find((e) => e.code === "ICE")!.used = 8;
    expect(engineFigure(tied, [...DATA.cars.filter((c) => c.car_number !== 30), tied])?.line).toBe(
      "fitted against an allocation of 4.",
    );
    const one = clone(30);
    one.elements.find((e) => e.code === "ICE")!.used = 1;
    expect(engineFigure(one, DATA.cars)?.unit).toBe("engine");
    const unstated = clone(30);
    unstated.elements.find((e) => e.code === "ICE")!.allowance = null;
    expect(engineFigure(unstated, DATA.cars)?.line).toBe("fitted; the FIA has not stated the allocation yet.");
    const none = clone(30);
    none.elements = none.elements.filter((e) => e.code !== "ICE");
    expect(engineFigure(none, DATA.cars)).toBeNull();
  });
});

describe("lineup", () => {
  it("tells the regular driver's rounds and the stand-in's, with what the stewards ruled at each", () => {
    const [had, law] = lineup(car(6));
    expect(had).toMatchObject({
      standIn: false,
      first: { bold: "17 rounds", rest: " · R1–R11, R15–R20" },
      rulings: "−35 grid places, 2 pit-lane starts",
    });
    expect(law).toMatchObject({
      standIn: true,
      first: { bold: "R12–R14", rest: " · under his own number" },
      rulings: "−35 grid places",
    });
  });

  it("covers three drivers of one car, singular rounds, and no ruling", () => {
    expect(lineup(car(51)).map((seat) => [seat.first.bold, seat.first.rest, seat.rulings])).toEqual([
      ["18 rounds", " · R1–R18", "no ruling"],
      ["R19", " · under his own number", "no ruling"],
      ["1 round", " · R20", "no ruling"],
    ]);
  });

  it("names back-of-grid starts, and a stand-in who wears the car's own number", () => {
    const changed = clone(6);
    changed.drivers[1].car_number = changed.car_number;
    for (const event of changed.events) {
      if (event.driver?.code === "HAD")
        event.decisions = event.decisions.map((d) => ({ ...d, outcome: "back_of_grid" }));
    }
    const [had, law] = lineup(changed);
    expect(had.rulings).toBe("4 back-of-grid starts");
    expect(law.first.rest).toBe("");
    const one = clone(6);
    one.events = one.events.slice(0, 1);
    one.events[0].driver = one.drivers[0];
    one.events[0].decisions = [{ ...one.events[0].decisions[0], outcome: "back_of_grid" }];
    expect(lineup(one)[0].rulings).toBe("1 back-of-grid start");
  });
});

describe("carKpis", () => {
  it("car 6: the grid drops in round order, the pit-lane rounds, and the extra units by element", () => {
    const [places, pit, over, extra] = carKpis(car(6), ROUNDS);
    expect(places).toEqual({ label: "Grid places imposed", value: "70", sub: "R10 −30 · R13 −35 · R16 −5" });
    expect(pit).toEqual({
      label: "Pit-lane starts",
      value: "2",
      sub: "ordered by power-unit rulings · R4 Miami GP · R17 Singapore GP",
    });
    expect(over).toEqual({
      label: "Elements over",
      value: "7",
      unit: "of 7",
      sub: "every element past its allocation",
    });
    expect(extra.value).toBe("15");
    expect(extra.sub).toBe("beyond the allocation · ICE 4 · TC 3 · EXH 3 · PU-ANC 2 · MGU-K 1 · ES 1 · PU-CE 1");
  });

  it("car 30: no drop, a weekend with no ruling found, some elements over", () => {
    const [places, pit, over, extra] = carKpis(car(30), ROUNDS);
    expect(places.sub).toBe("no grid drop · 1 weekend past the allocation with no ruling found");
    expect(pit).toMatchObject({ value: "0", sub: "ordered by power-unit rulings" });
    expect(over).toMatchObject({ value: "4", unit: "of 7", sub: "elements past their allocation" });
    expect(extra.sub).toBe("beyond the allocation · ICE 1 · TC 1 · EXH 1 · PU-ANC 1");
  });

  it("car 51: every element within, nothing extra", () => {
    const [places, , over, extra] = carKpis(car(51), ROUNDS);
    expect(places).toMatchObject({ value: "0", sub: "no grid drop" });
    expect(over).toMatchObject({ value: "0", sub: "every element within its allocation" });
    expect(extra).toMatchObject({ value: "0", sub: "beyond the allocation" });
  });

  it("adds a pending ruling, back-of-grid starts, and falls back to the round number without a name", () => {
    const changed = clone(6);
    changed.penalties = { ...changed.penalties, pending: 1, back_of_grid: 2 };
    const [places, pit] = carKpis(changed, new Map());
    expect(places.sub).toBe("R10 −30 · R13 −35 · R16 −5 · 1 weekend's ruling still pending");
    expect(pit.sub).toBe("ordered by power-unit rulings · R4 · R17 · plus 2 from the back of the grid");
  });
});

describe("units the documents do not place", () => {
  it("counts a drop with no places as none, and a unit with neither round nor window as no window", () => {
    const changed = clone(12);
    for (const event of changed.events) {
      event.driver = changed.drivers[0];
      event.decisions = event.decisions.map((decision) => ({ ...decision, places: null }));
    }
    changed.elements[0].parts[0].round = null;
    changed.elements[0].parts[0].window = null;
    expect(lineup(changed)[0].rulings).toBe("no ruling");
    expect(carKpis(changed, ROUNDS)[0].sub).toMatch(/^R\d+ −0/);
    expect(timelineSub(changed, 20).tail).toBe("");
  });
});

describe("ledger", () => {
  it("titles by how many elements are over", () => {
    expect(ledgerTitle(car(6))).toBe("All seven elements past the allocation");
    expect(ledgerTitle(car(30))).toBe("Four of seven elements past the allocation");
    expect(ledgerTitle(car(51))).toBe("Every element within the allocation");
    expect(ledgerTitle(car(12))).toBe("Three of seven elements past the allocation");
  });

  it("splits counted units by the backend's flag, leaves spares, and sets aside the uncounted", () => {
    const exhaust = ledgerRows(car(12), DATA.elements ?? []).find((row) => row.usage.code === "EXH")!;
    expect(exhaust.within.map((p) => p.number)).toEqual([1, 2, 3]);
    expect(exhaust.spares).toBe(1);
    expect(exhaust.notCounted.map((p) => p.number)).toEqual([4]);
    expect(exhaust.name).toBe(DATA.elements?.find((e) => e.code === "EXH")?.name);
    const ice = ledgerRows(car(6), []).find((row) => row.usage.code === "ICE")!;
    expect(ice.beyond).toHaveLength(4);
    expect(ice.spares).toBe(0);
    expect(ice.name).toBe("ICE");
  });

  it("offers no spares when the allowance is not stated", () => {
    const changed = clone(12);
    changed.elements[0].allowance = null;
    expect(ledgerRows(changed, [])[0].spares).toBe(0);
  });

  it("labels a tile with its side, whether it counts, and where it arrived", () => {
    const six = car(6);
    expect(tileLabel(part(six, "ICE", 1), ROUNDS)).toBe(
      "ICE unit 1, within the allocation: Introduced at the Australian GP (the only round between two FIA usage reports)",
    );
    expect(tileLabel(part(car(12), "EXH", 4), ROUNDS)).toContain("within the allocation, not counted: ");
    expect(tileLabel(part(six, "ICE", 8), ROUNDS)).toContain("ICE unit 8, beyond the allocation: ");
  });

  it("selects the newest unit, beyond the allocation first", () => {
    expect(defaultPart(car(6))).toEqual({ code: "ICE", number: 8 });
    expect(defaultPart(car(18))).toEqual({ code: "TC", number: 6 });
    expect(defaultPart({ ...car(6), elements: [] })).toBeNull();
  });
});

describe("inspector", () => {
  it("heads a unit by where it stands against the allocation", () => {
    const six = car(6);
    expect(inspectorHead(part(six, "ICE", 8), six.elements[0])).toBe("ICE #8 · 4th beyond the 4 allowed");
    expect(inspectorHead(part(six, "ICE", 2), six.elements[0])).toBe("ICE #2 · within the 4 allowed");
    const twelve = car(12);
    const exhaust = twelve.elements.find((e) => e.code === "EXH")!;
    expect(inspectorHead(part(twelve, "EXH", 4), exhaust)).toBe("EXH #4 · not counted");
    expect(inspectorHead(part(six, "ICE", 8), { ...six.elements[0], allowance: null })).toBe(
      "ICE #8 · allowance not stated",
    );
  });

  it("gives the ruling for a unit, in order of what the data shows", () => {
    const six = car(6);
    expect(rulingFor(part(six, "ICE", 8), six.events)).toBe("Stewards: Pit-lane start, first used in Qualifying.");
    expect(rulingFor(part(six, "ICE", 2), six.events)).toBe("No penalty: within the season's allocation.");
    expect(rulingFor(part(car(12), "EXH", 4), car(12).events)).toBe(
      "The FIA's usage reports stopped counting this unit from round 13, so it is not in the total.",
    );
    const eighteen = car(18);
    expect(rulingFor(part(eighteen, "ICE", 6), eighteen.events)).toBe(
      "No stewards' decision can be matched to this unit: the documents collected do not pin its round down.",
    );
    const thirty = car(30);
    expect(rulingFor(part(thirty, "ICE", 5), thirty.events)).toBe(
      "No stewards' decision naming this unit was found in the collected documents.",
    );
    const pending: CarEvent[] = thirty.events.map((event) => ({ ...event, penalty_status: "pending" }));
    expect(rulingFor(part(thirty, "ICE", 5), pending)).toBe(
      "The stewards' decision for this weekend has not been published yet.",
    );
  });

  it("omits the session when the decision has none", () => {
    const six = car(6);
    const events = six.events.map((event) => ({
      ...event,
      decisions: event.decisions.map((d) => ({ ...d, session: null })),
    }));
    expect(rulingFor(part(six, "ICE", 8), events)).toBe("Stewards: Pit-lane start.");
  });
});

describe("season panel", () => {
  it("titles the rulings in words, by kind", () => {
    expect(timelineTitle(car(6), 20)).toBe("Five rulings in 20 rounds: three grid drops and two pit-lane starts");
    expect(timelineTitle(car(18), 20)).toBe("Five rulings in 20 rounds: four grid drops and one pit-lane start");
    expect(timelineTitle(car(12), 20)).toBe("One ruling in 20 rounds: one grid drop");
    expect(timelineTitle(car(30), 20)).toBe("No power-unit ruling in 20 rounds");
    expect(timelineTitle(car(30), null)).toBe("No power-unit ruling this season");
    expect(timelineTitle(car(12), 1)).toBe("One ruling in 1 round: one grid drop");
  });

  it("lists back-of-grid starts and other rulings", () => {
    const changed = clone(6);
    const [first, second] = changed.events.flatMap((event) => event.decisions);
    first.outcome = "back_of_grid";
    second.outcome = "other";
    expect(timelineTitle(changed, 20)).toContain("one back-of-grid start and one other ruling");
  });

  it("says how many weekends fitted units, who stood in, and which units have no round", () => {
    expect(timelineSub(car(6), 20)).toMatchObject({
      head: "New units fitted at 10 of 20 Grand Prix weekends",
      standIns: [{ runs: "R12–R14" }],
      tail: "",
    });
    expect(timelineSub(car(30), 20).tail).toBe(" · 1 weekend past the allocation with no ruling found");
    expect(timelineSub(car(18), 20)).toMatchObject({
      head: "New units fitted at 12 of 20 Grand Prix weekends",
      tail: " · 5 units arrived between R18 and R19, round not pinned down",
    });
    expect(timelineSub(car(12), null).head).toBe("New units fitted at 6 Grand Prix weekends");
    expect(timelineSub({ ...car(6), penalties: { ...car(6).penalties, pending: 2 } }, 20).tail).toBe(
      " · 2 weekends' rulings still pending",
    );
  });

  it("makes one cell per round, marked by what it cost", () => {
    const cells = seasonCells(DATA, car(6));
    expect(cells).toHaveLength(23);
    expect(cells.slice(0, 20).map((cell) => `${cell.code} ${cell.text}`)).toEqual([
      "AUS 7",
      "CHN 9",
      "JPN ·",
      "MIA PL",
      "CAN 4",
      "MCO ·",
      "BAR ·",
      "AUT 4",
      "GBR ·",
      "BEL −30",
      "HUN ·",
      "NLD 1",
      "ITA −35",
      "ESP ·",
      "AZE ·",
      "BHR −5",
      "SGP PL",
      "USA ·",
      "MEX ·",
      "SAO ·",
    ]);
    expect(cells[19].latest).toBe(true);
    expect(cells[20]).toMatchObject({ kind: "future", text: "" });
    expect(cells[20].label).toContain("no FIA documents yet");
    expect(cells[3]).toMatchObject({ kind: "penalty", label: "Miami GP: pit-lane start" });
    expect(cells[9]).toMatchObject({ kind: "penalty", label: "Belgian GP: 30 grid places" });
    expect(cells[2]).toMatchObject({ kind: "nothing", label: "Japanese GP: nothing new" });
    expect(cells[0]).toMatchObject({ kind: "units", label: "Australian GP: 7 new units" });
    expect(cells[11]).toMatchObject({ label: "Dutch GP: 1 new unit" });
    expect(cells.filter((cell) => cell.driver?.standIn).map((cell) => cell.code)).toEqual(["NLD", "ITA", "ESP"]);
    expect(cells[0].driver).toEqual({ code: "HAD", standIn: false });
    expect(cells[20].driver).toBeNull();
  });

  it("marks a ruling not found, a ruling pending, and units whose round is not pinned down", () => {
    expect(seasonCells(DATA, car(30)).find((cell) => cell.code === "MEX")).toMatchObject({
      kind: "notFound",
      text: "!",
    });
    const pending = clone(30);
    for (const event of pending.events) if (event.penalty_status === "not_found") event.penalty_status = "pending";
    expect(seasonCells(DATA, pending).find((cell) => cell.code === "MEX")).toMatchObject({
      kind: "pending",
      text: "?",
      label: "Mexican GP: stewards' decision pending",
    });
    expect(seasonCells(DATA, car(30)).find((cell) => cell.code === "MEX")?.label).toBe(
      "Mexican GP: no stewards' decision found",
    );
    const windowed = seasonCells(DATA, car(18)).filter((cell) => cell.kind === "window");
    expect(windowed.map((cell) => [cell.code, cell.text])).toEqual([
      ["USA", "5"],
      ["MEX", "5"],
    ]);
    expect(windowed[0].label).toBe(
      "United States GP: 5 new units arrived at this round or another between R18 and R19 (round not pinned down)",
    );
  });

  it("spans the windows of several units, and has no latest round without as_of", () => {
    const changed = clone(18);
    const unit = changed.elements.flatMap((e) => e.parts).find((p) => p.window !== null)!;
    unit.window = [17, 19];
    expect(seasonCells(DATA, changed).find((cell) => cell.code === "USA")?.label).toContain("between R17 and R19");
    expect(seasonCells({ ...DATA, as_of: null, rounds: undefined }, car(6))).toEqual([]);
    expect(seasonCells({ ...DATA, as_of: null }, car(6)).some((cell) => cell.latest)).toBe(false);
  });

  it("falls back to R-number for a round with no code", () => {
    const data = { ...DATA, rounds: [{ round: 1, name: "X GP", code: "", date: "2026-03-01", has_documents: true }] };
    expect(seasonCells(data, car(6))[0].code).toBe("R1");
  });
});

describe("weekend log", () => {
  it("counts the weekends with new units, and says nothing for none", () => {
    expect(weekendsAside(car(6))).toBe("10 weekends with new units · newest first");
    expect(weekendsAside({ ...car(6), events: car(6).events.slice(0, 1) })).toBe(
      "1 weekend with new units · newest first",
    );
    expect(weekendsAside({ ...car(6), events: [] })).toBeUndefined();
  });

  it("words a decision", () => {
    const decision = car(6).events.find((event) => event.round === 17)!.decisions[0];
    expect(decisionLine(decision)).toBe("ICE #8 · TC #7 · EXH #7 · PU-ANC #8 · first used in Qualifying");
    expect(decisionLine({ ...decision, session: null })).toBe("ICE #8 · TC #7 · EXH #7 · PU-ANC #8");
    expect(nominalNote(decision)).toBe(
      "The units alone carried 5 grid places; the pit-lane start made that drop redundant.",
    );
    expect(nominalNote({ ...decision, nominal_places: null })).toBeNull();
    expect(nominalNote({ ...decision, outcome: "grid_drop" })).toBeNull();
  });

  it("words the gap when no ruling is on file", () => {
    expect(gapNote("pending")).toBe(
      "Units beyond the allocation were fitted, and the stewards have not published a decision yet.",
    );
    expect(gapNote("not_found")).toBe(
      "Units beyond the allocation were fitted, but no stewards' decision naming them was found in the collected documents.",
    );
    expect(gapNote("decided")).toBeNull();
    expect(gapNote("none")).toBeNull();
  });

  it("sets a document title with dots", () => {
    expect(docLabel("Doc 83 - Infringement - Car 6")).toBe("Doc 83 · Infringement · Car 6");
  });
});

describe("source note", () => {
  it("gives the source line with the times when they are known", () => {
    expect(sourceLine(DATA.freshness)).toBe(
      'Source: FIA technical-delegate reports "New PU elements for this competition" and the stewards\' power-unit decisions, checked hourly · last checked 18 Nov 2026, 14:36 UTC · last change 08 Nov 2026, 19:41 UTC',
    );
    expect(sourceLine(null)).toMatch(/checked hourly$/);
    expect(sourceLine({ ...DATA.freshness!, checked_at: null, changed_at: null })).toMatch(/checked hourly$/);
  });

  it("groups allocations by the document that stated them", () => {
    expect(allocationGroups(DATA.elements ?? [])).toEqual([
      expect.objectContaining({ codes: "ICE 4 · TC 4 · ES 3 · PU-CE 3", doc: "FIA doc 55, 8 Nov" }),
      expect.objectContaining({ codes: "EXH 4 · MGU-K 3 · PU-ANC 6", doc: "FIA doc 42, 8 Nov" }),
    ]);
    expect(allocationGroups(DATA.elements ?? [])[0].url).toMatch(/^https:\/\/www\.fia\.com\//);
  });

  it("keeps hand-pinned and unstated allocations apart, without a link", () => {
    const [ice, tc] = DATA.elements ?? [];
    const es = DATA.elements!.find((item) => item.code === "ES")!;
    const groups = allocationGroups([
      { ...ice, allowance_source: { ...ice.allowance_source!, kind: "manual" } },
      { ...tc, allowance: null, allowance_source: null },
      { ...es, allowance_source: { ...es.allowance_source!, title: null, stated_on: null, url: null } },
    ]);
    expect(groups.map((g) => [g.codes, g.doc, g.url === null])).toEqual([
      ["ICE 4", null, true],
      ["TC ?", null, true],
      ["ES 3", "FIA document", true],
    ]);
  });

  it("adds the car's own warnings to the page's notes", () => {
    expect(carNotes(DATA, car(6))).toEqual([]);
    expect(carNotes(DATA, { ...car(6), warnings: ["Counts differ."] })).toEqual([{ text: "Counts differ." }]);
  });
});
