import { describe, expect, it } from "vitest";

import { POWER_UNITS_2026, TEAMS_2026 } from "@/test/fixtures";

import {
  gridPlaceRanking,
  heroModel,
  kpis,
  latestPenalty,
  listSeparator,
  plural,
  rankingTitle,
  rulingSuffix,
  sharedSeatStory,
  sourceNotes,
  standingsOrder,
} from "./seasonModel";

import type { Decision, PowerUnitCar, PowerUnitsResponse } from "./powerUnitsModel";
import type { TeamsResponse } from "../standings/teamsModel";

const DATA = POWER_UNITS_2026;

function car(data: PowerUnitsResponse, number: number): PowerUnitCar {
  const found = data.cars.find((item) => item.car_number === number);
  if (!found) throw new Error(`no car ${number}`);
  return found;
}

describe("plural and rulingSuffix", () => {
  it("pluralises, and words the rulings still to come", () => {
    expect([plural(1), plural(2)]).toEqual(["", "s"]);
    expect(rulingSuffix(0, 0)).toBe("");
    expect(rulingSuffix(1, 0)).toBe(" · 1 weekend's ruling still pending");
    expect(rulingSuffix(2, 1)).toBe(
      " · 2 weekends' rulings still pending · 1 weekend past the allocation with no ruling found",
    );
  });
});

describe("heroModel", () => {
  it("names the round and the latest FIA document, and says engines are over", () => {
    expect(heroModel(DATA)).toEqual({
      eyebrow: "Power units · 2026 · after round 20 · latest FIA document: São Paulo GP doc 57",
      title: "Engines over the limit",
    });
  });

  it("drops the document number when it has none, and the whole clause without an as_of", () => {
    const noNumber = (() => {
      const d = structuredClone(DATA);

      if (d.as_of) d.as_of.number = null;

      return d;
    })();
    expect(heroModel(noNumber).eyebrow).toBe("Power units · 2026 · after round 20 · latest FIA document: São Paulo GP");
    expect(
      heroModel(
        (() => {
          const d = structuredClone(DATA);
          d.as_of = null;
          return d;
        })(),
      ).eyebrow,
    ).toBe("Power units · 2026");
  });

  it("falls back to the round number when the round list lacks it", () => {
    expect(
      heroModel(
        (() => {
          const d = structuredClone(DATA);
          d.rounds = [];
          return d;
        })(),
      ).eyebrow,
    ).toContain("document: round 20");
  });

  it("says every engine is within the allocation when none is over", () => {
    const within = (() => {
      const d = structuredClone(DATA);

      for (const item of d.cars) for (const element of item.elements) element.over_by = 0;

      return d;
    })();
    expect(heroModel(within).title).toBe("Every engine within the allocation");
  });
});

describe("kpis", () => {
  it("counts the season from the payload", () => {
    const [places, engines, pitLane] = kpis(DATA);
    expect(places).toEqual({
      label: "Grid places imposed",
      value: "685",
      sub: "by power-unit penalties this season · 2 weekends past the allocation with no ruling found",
    });
    expect(engines).toEqual({
      label: "Over on engines",
      value: "15",
      unit: "of 22",
      sub: "cars past the 4-engine allocation",
    });
    expect(pitLane).toEqual({ label: "Pit-lane starts", value: "7", sub: "from power-unit changes" });
  });

  it("words one and several pending rulings, and one ruling not found", () => {
    const withTotals = (pending: number, notFound: number) =>
      (() => {
        const d = structuredClone(DATA);

        for (const item of d.cars) item.penalties = { ...item.penalties, pending: 0, not_found: 0 };
        d.cars[0].penalties.pending = pending;
        d.cars[0].penalties.not_found = notFound;

        return d;
      })();
    expect(kpis(withTotals(1, 1))[0].sub).toBe(
      "by power-unit penalties this season · 1 weekend's ruling still pending · 1 weekend past the allocation with no ruling found",
    );
    expect(kpis(withTotals(2, 0))[0].sub).toBe(
      "by power-unit penalties this season · 2 weekends' rulings still pending",
    );
  });

  it("adds the back-of-grid starts", () => {
    const back = (() => {
      const d = structuredClone(DATA);
      d.cars[0].penalties.back_of_grid = 2;
      return d;
    })();
    expect(kpis(back)[2].sub).toBe("from power-unit changes · plus 2 from the back of the grid");
  });

  it("counts no car over when none is, and leaves the allowance out when it is not known", () => {
    const none = (() => {
      const d = structuredClone(DATA);

      for (const item of d.cars) for (const element of item.elements) element.over_by = 0;
      for (const element of d.elements ?? []) if (element.code === "ICE") element.allowance = null;

      return d;
    })();
    expect(kpis(none)[1]).toMatchObject({ value: "0", sub: "cars past the engine allocation" });
    expect(
      kpis(
        (() => {
          const d = structuredClone(DATA);
          d.elements = undefined;
          return d;
        })(),
      )[1].sub,
    ).toBe("cars past the engine allocation");
  });
});

describe("latestPenalty", () => {
  it("is the newest decision, as a grid drop", () => {
    const latest = latestPenalty(DATA);
    expect(latest).toMatchObject({
      value: "−10",
      detail: "São Paulo GP · ES, PU-CE (FIA doc 57)",
    });
    expect(latest?.driver.name).toContain("Bortoleto");
  });

  it("is null with no decision", () => {
    const none = (() => {
      const d = structuredClone(DATA);

      for (const item of d.cars) for (const event of item.events) event.decisions = [];

      return d;
    })();
    expect(latestPenalty(none)).toBeNull();
  });

  /** Every decision of the latest round patched, so whichever the log puts first is the patched one. */
  function withLatest(patch: Partial<Decision>, dropRounds = false): PowerUnitsResponse {
    const d = structuredClone(DATA);
    for (const item of d.cars) {
      for (const event of item.events.filter((entry) => entry.round === 20)) {
        for (const decision of event.decisions) Object.assign(decision, patch);
      }
    }
    if (dropRounds) d.rounds = [];
    return d;
  }

  it("reads a pit-lane start in words, and a missing document number and round name", () => {
    const pit = withLatest({ outcome: "pit_lane", number: null }, true);
    expect(latestPenalty(pit)).toMatchObject({ value: "Pit-lane start" });
    expect(latestPenalty(pit)?.detail).toMatch(/^round 20 · [A-Z, -]+$/);
  });

  it("reads a grid drop with no places as zero, and falls back to the car's driver", () => {
    const zero = (() => {
      const d = structuredClone(DATA);

      for (const item of d.cars) {
        for (const event of item.events) {
          if (event.round === 20 && event.decisions.length > 0) {
            event.driver = null;
            for (const decision of event.decisions) decision.places = null;
          }
        }
      }

      return d;
    })();
    expect(latestPenalty(zero)?.value).toBe("−0");
    expect(latestPenalty(zero)?.driver.name).toBeTruthy();
  });
});

describe("standingsOrder", () => {
  const BY_NUMBER = [12, 63, 44, 16, 3, 6, 1, 81, 30, 41, 10, 43, 87, 51, 5, 27, 55, 23, 14, 18, 77, 11];

  it("is the constructors' order, each team's better-placed car first", () => {
    const order = standingsOrder(DATA.cars, TEAMS_2026);
    expect(order.byStandings).toBe(true);
    expect(order.cars.map((item) => item.car_number)).toEqual(BY_NUMBER);
  });

  it("is by car number without a table, and never reorders the input", () => {
    const before = DATA.cars.map((item) => item.car_number);
    for (const teams of [undefined, { ...TEAMS_2026, teams: [] } as TeamsResponse]) {
      const order = standingsOrder(DATA.cars, teams);
      expect(order.byStandings).toBe(false);
      expect(order.cars.map((item) => item.car_number)).toEqual([...before].sort((a, b) => a - b));
    }
    expect(DATA.cars.map((item) => item.car_number)).toEqual(before);
  });

  it("puts a car whose team or drivers are not in the table last", () => {
    const stranger = {
      ...car(DATA, 12),
      car_number: 99,
      team_id: "nobody",
      drivers: [{ ...car(DATA, 12).drivers[0], code: "ZZZ" }],
    };
    const order = standingsOrder([stranger, car(DATA, 12)], TEAMS_2026).cars;
    expect(order.map((item) => item.car_number)).toEqual([12, 99]);
    const sameTeam = { ...car(DATA, 12), car_number: 98, drivers: [{ ...car(DATA, 12).drivers[0], code: "ZZZ" }] };
    expect(standingsOrder([sameTeam, car(DATA, 12)], TEAMS_2026).cars.map((item) => item.car_number)).toEqual([12, 98]);
  });

  it("ignores table rows with no driver code", () => {
    const codeless: TeamsResponse = {
      ...TEAMS_2026,
      teams: TEAMS_2026.teams.map((team) => ({
        ...team,
        drivers: team.drivers.map(({ code: _code, ...rest }) => rest),
      })),
    };
    expect(standingsOrder(DATA.cars, codeless).cars).toHaveLength(22);
  });
});

describe("gridPlaceRanking and rankingTitle", () => {
  it("ranks the cars that lost places, ties by car number", () => {
    const ranked = gridPlaceRanking(DATA.cars);
    expect(ranked).toHaveLength(16);
    expect(ranked.map((item) => [item.car_number, item.penalties.grid_places])).toEqual([
      [5, 90],
      [18, 80],
      [44, 75],
      [6, 70],
      [63, 65],
      [14, 50],
      [77, 50],
      [41, 45],
      [3, 30],
      [11, 30],
      [12, 30],
      [23, 20],
      [43, 20],
      [1, 10],
      [16, 10],
      [55, 10],
    ]);
  });

  it("names the one car on top", () => {
    expect(rankingTitle(gridPlaceRanking(DATA.cars))).toBe("Car #5 has the most grid-place penalties");
  });

  it("never names one car for a tie of two or three", () => {
    const tie = (...numbers: number[]) =>
      (() => {
        const d = structuredClone(DATA);

        for (const item of d.cars) item.penalties.grid_places = numbers.includes(item.car_number) ? 100 : 0;

        return d;
      })().cars;
    expect(rankingTitle(gridPlaceRanking(tie(5, 18)))).toBe("Cars #5 and #18 share the most grid-place penalties");
    expect(rankingTitle(gridPlaceRanking(tie(5, 18, 44)))).toBe(
      "Cars #5, #18 and #44 share the most grid-place penalties",
    );
  });

  it("separates a list", () => {
    expect([0, 1, 2].map((index) => listSeparator(index, 3))).toEqual(["", ", ", " and "]);
  });
});

describe("sharedSeatStory", () => {
  it("tells car 6: Hadjar's, with Lawson in rounds 12 to 14", () => {
    const story = sharedSeatStory(DATA.cars);
    expect(story?.car.car_number).toBe(6);
    expect(story?.regular.code).toBe("HAD");
    expect(story?.others.map((other) => [other.code, other.car_number])).toEqual([["LAW", 30]]);
    expect(story?.except).toBe("R12–R14");
  });

  it("finds the three shared seats the capture has", () => {
    expect(
      DATA.cars
        .filter((item) => item.drivers.length > 1)
        .map((item) => item.car_number)
        .sort((a, b) => a - b),
    ).toEqual([6, 30, 51]);
  });

  it("takes a later stint with more rounds as the regular", () => {
    const flipped = DATA.cars
      .filter((item) => item.car_number === 6)
      .map((item) => ({ ...item, drivers: [...item.drivers].reverse() }));
    expect(sharedSeatStory(flipped)?.regular.code).toBe("HAD");
  });

  it("is null with no shared seat", () => {
    expect(sharedSeatStory(DATA.cars.map((item) => ({ ...item, drivers: item.drivers.slice(0, 1) })))).toBeNull();
  });

  it("takes a three-driver seat, the regular being who raced the most rounds", () => {
    const story = sharedSeatStory(DATA.cars.filter((item) => item.car_number === 51));
    expect(story?.car.drivers).toHaveLength(3);
    expect(story?.others).toHaveLength(2);
    expect(story?.regular.rounds.length).toBeGreaterThan(story?.others[0].rounds.length ?? 99);
  });

  it("breaks ties between seats by car number, and takes the first stint on a tie of rounds", () => {
    const flat = DATA.cars
      .filter((item) => item.drivers.length > 1)
      .map((item) => ({
        ...item,
        penalties: { ...item.penalties, grid_places: 10 },
        drivers: item.drivers.map((stint) => ({ ...stint, rounds: [1] })),
      }));
    const story = sharedSeatStory(flat);
    expect(story?.car.car_number).toBe(6);
    expect(story?.regular).toBe(story?.car.drivers[0]);
  });
});

describe("sourceNotes", () => {
  it("has nothing to say about the capture", () => {
    expect(sourceNotes(DATA)).toEqual([]);
  });

  const freshness = (change: Partial<NonNullable<PowerUnitsResponse["freshness"]>>) =>
    (() => {
      const d = structuredClone(DATA);

      if (d.freshness) Object.assign(d.freshness, change);

      return d;
    })();

  it("says how the collection stands", () => {
    const when = "18 Nov 2026, 14:36 UTC";
    expect(sourceNotes(freshness({ outcome: "aborted" }))).toEqual([
      { text: `Last check failed · last checked ${when}` },
    ]);
    expect(sourceNotes(freshness({ outcome: "write_failed" }))[0].text).toBe(
      `Last check not saved · last checked ${when}`,
    );
    expect(sourceNotes(freshness({ stale: true }))[0].text).toBe(`Collection overdue · last checked ${when}`);
    expect(sourceNotes(freshness({ outcome: "document_failures" }))[0].text).toBe(
      `Some documents unread · last checked ${when}`,
    );
    expect(sourceNotes(freshness({ checked_at: null }))).toEqual([{ text: "Not checked yet" }]);
    expect(
      sourceNotes(
        (() => {
          const d = structuredClone(DATA);
          d.freshness = null;
          return d;
        })(),
      ),
    ).toEqual([]);
  });

  it("lists unread and withdrawn documents with their links, and the warnings", () => {
    const data = (() => {
      const d = structuredClone(DATA);

      d.unread = [{ event: "Monaco", title: "Doc 9", url: "https://fia/9", reason: "scanned image" }];
      d.withdrawn = [{ title: "Doc 7", url: "https://fia/7", reason: "replaced" }];
      d.warnings = ["Car 5 totals disagree"];

      return d;
    })();
    expect(sourceNotes(data)).toEqual([
      {
        text: "Monaco: Doc 9 could not be read (scanned image); counts that depend on it may be incomplete",
        url: "https://fia/9",
      },
      { text: "Doc 7: withdrawn or replaced by the FIA, not counted (replaced)", url: "https://fia/7" },
      { text: "Car 5 totals disagree" },
    ]);
    expect(
      sourceNotes(
        (() => {
          const d = structuredClone(DATA);
          d.withdrawn = undefined;
          return d;
        })(),
      ),
    ).toEqual([]);
    expect(
      sourceNotes(
        (() => {
          const d = structuredClone(DATA);
          d.elements = undefined;
          return d;
        })(),
      ),
    ).toEqual([]);
  });

  it("appends the collection error to the collection line, and only there", () => {
    const failed = structuredClone(DATA);
    failed.freshness = { ...failed.freshness!, outcome: "aborted", error: "fia.com timed out" };
    expect(sourceNotes(failed)[0].text).toMatch(/^Last check failed · last checked .* · fia\.com timed out$/);

    const quiet = structuredClone(DATA);
    quiet.freshness = { ...quiet.freshness!, error: "stale error" };
    expect(sourceNotes(quiet)).toEqual([]);
  });

  it("flags allowances that are missing or pinned by hand", () => {
    const data = (() => {
      const d = structuredClone(DATA);

      const [first, second, third] = d.elements ?? [];
      first.allowance_source = null;
      if (second.allowance_source)
        second.allowance_source = { ...second.allowance_source, kind: "manual", note: "per Doc 3" };
      if (third.allowance_source) third.allowance_source = { ...third.allowance_source, kind: "manual", note: null };

      return d;
    })();
    const [a, b, c] = sourceNotes(data);
    expect(a.text).toBe("ICE: allowance not stated by the FIA yet");
    expect(b.text).toMatch(/: allowance pinned by hand \(per Doc 3\)$/);
    expect(c.text).toMatch(/: allowance pinned by hand$/);
  });
});
