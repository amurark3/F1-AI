import { describe, expect, it } from "vitest";

import { CLINCH_2026 } from "@/test/fixtures";

import {
  clinchAside,
  contenderName,
  decidedSentence,
  entrantClause,
  heroSentence,
  nextEventSentence,
  stayInItSentence,
  type ClinchNeed,
  type DecidedAt,
  type TitleClinch,
} from "./clinch";

const need = (name: string, margin: number, countback = false, code: string | null = null): ClinchNeed => ({
  name,
  code,
  team: name,
  margin,
  countback,
});

const ANT = { name: "Kimi Antonelli", code: "ANT" };
const NOR = { name: "Lando Norris", code: "NOR" };
const RUS = need("George Russell", -23, false, "RUS");
const HAM = need("Lewis Hamilton", -24, false, "HAM");

const decided = (over: Partial<DecidedAt>): DecidedAt => ({
  round: 19,
  name: "Mexican Grand Prix",
  venue: "Mexico City",
  lead: 119,
  left: 100,
  races_to_spare: 4,
  sprints_to_spare: 0,
  provisional: false,
  ...over,
});

const open = (over: Partial<TitleClinch> = {}, possible = true, needs: ClinchNeed[] = [RUS]): TitleClinch => ({
  decided: false,
  leader: { ...ANT, team: "Mercedes", points: 365 },
  max_available: 125,
  next: {
    round: 19,
    name: "Mexican Grand Prix",
    venue: "Mexico City",
    races: 1,
    sprints: 0,
    max_points: 25,
    possible,
    needs,
  },
  earliest: { round: 21, name: "Las Vegas Grand Prix", venue: "Las Vegas" },
  decided_at: null,
  ...over,
});

describe("nextEventSentence", () => {
  it("names the one rival a team must outscore", () => {
    expect(nextEventSentence("constructors", { name: "Mercedes", code: null }, "São Paulo", [need("Ferrari", 3)])).toBe(
      "Mercedes clinch in São Paulo if they outscore Ferrari by 3.",
    );
  });

  it("lists every rival that can still beat the leader, with the count-back figure", () => {
    expect(
      nextEventSentence(
        "drivers",
        ANT,
        "Mexico City",
        [RUS, HAM].map((n) => ({ ...n })),
      ),
    ).toBe(
      "Kimi Antonelli clinches in Mexico City unless George Russell outscores them by 24 or more, or Lewis Hamilton outscores them by 25 or more.",
    );
    expect(
      nextEventSentence("drivers", ANT, "Austin", [
        need("George Russell", 24, true, "RUS"),
        need("Lewis Hamilton", 14, false, "HAM"),
        need("Max Verstappen", 7, true, "VER"),
        need("Charles Leclerc", 0, false, "LEC"),
        need("Lando Norris", -14, false, "NOR"),
      ]),
    ).toBe(
      "Kimi Antonelli clinches in Austin if they outscore George Russell by 24 (23 on count-back), Lewis Hamilton by 14 and Max Verstappen by 7 (6 on count-back), unless Charles Leclerc outscores them by 1 or more, or Lando Norris outscores them by 15 or more.",
    );
    expect(
      nextEventSentence("drivers", NOR, "Lusail", [
        need("Oscar Piastri", 2, true, "PIA"),
        need("Max Verstappen", 2, true, "VER"),
      ]),
    ).toBe(
      "Lando Norris clinches in Lusail if they outscore Oscar Piastri by 2 (1 on count-back) and Max Verstappen by 2 (1 on count-back).",
    );
    expect(
      nextEventSentence("drivers", NOR, "Abu Dhabi", [
        need("Max Verstappen", -11, true, "VER"),
        need("Oscar Piastri", -15, true, "PIA"),
      ]),
    ).toBe(
      "Lando Norris clinches in Abu Dhabi unless Max Verstappen outscores them by 13 or more (12 goes to count-back), or Oscar Piastri outscores them by 17 or more (16 goes to count-back).",
    );
    expect(
      nextEventSentence("constructors", { name: "McLaren", code: null }, "Singapore", [
        need("Mercedes", -30),
        need("Ferrari", -34),
      ]),
    ).toBe(
      "McLaren clinch in Singapore unless Mercedes outscore them by 31 or more, or Ferrari outscore them by 35 or more.",
    );
  });

  it("has no conditions when nobody can still beat the leader", () => {
    expect(nextEventSentence("drivers", ANT, "Mexico City", [])).toBe("Kimi Antonelli clinches in Mexico City.");
  });
});

describe("decidedSentence", () => {
  const parts = (d: DecidedAt) => decidedSentence(d);

  it("says where, with what to spare and how far clear", () => {
    expect(parts(decided({}))).toEqual({
      strong: "Clinched in Mexico City",
      rest: " with four races to spare: 119 points clear, and only 100 left to win.",
    });
    expect(parts(decided({ lead: 142, left: 129, races_to_spare: 3 })).rest).toBe(
      " with three races to spare: 142 points clear, and only 129 left to win.",
    );
    expect(parts(decided({ lead: 325, left: 303, races_to_spare: 6, sprints_to_spare: 3 })).rest).toBe(
      " with six races and three sprints to spare: 325 points clear, and only 303 left to win.",
    );
    expect(parts(decided({ races_to_spare: 1 })).rest).toContain("with one race to spare");
    expect(parts(decided({ races_to_spare: 12 })).rest).toContain("with 12 races to spare");
  });

  it("says so at the final round, with nothing to spare", () => {
    expect(parts(decided({ venue: "Abu Dhabi", lead: 2, left: 0, races_to_spare: 0 }))).toEqual({
      strong: "Clinched in Abu Dhabi",
      rest: " at the final round, 2 points clear.",
    });
  });

  it("marks a provisional clinch", () => {
    expect(parts(decided({ provisional: true })).strong).toBe("Provisionally clinched in Mexico City");
  });
});

describe("heroSentence", () => {
  it("reads a decided title from where it was clinched", () => {
    const title = open({ decided: true, next: null, earliest: null, decided_at: decided({}) });
    expect(heroSentence("drivers", title)?.strong).toBe("Clinched in Mexico City");
  });

  it("falls back to a plain line when the clinch round is unknown", () => {
    const title = open({
      decided: true,
      next: null,
      earliest: null,
      leader: { name: "Mercedes", code: null, team: "Mercedes", points: 1 },
    });
    expect(heroSentence("constructors", title)).toEqual({ strong: "Mercedes have clinched the title", rest: "." });
    expect(
      heroSentence("drivers", { ...title, leader: { ...title.leader, name: "Kimi Antonelli", code: "ANT" } }),
    ).toEqual({
      strong: "Kimi Antonelli has clinched the title",
      rest: ".",
    });
  });

  it("reads what the leader must do when the title can be settled at the next event", () => {
    expect(heroSentence("drivers", open())).toEqual({
      strong: "",
      rest: "Kimi Antonelli clinches in Mexico City unless George Russell outscores them by 24 or more.",
    });
  });

  it("says when it cannot be settled next, and when it can at the earliest", () => {
    expect(heroSentence("drivers", open({}, false))).toEqual({
      strong: "",
      rest: "The title can't be settled in Mexico City. Kimi Antonelli can clinch in Las Vegas at the earliest.",
    });
  });

  it("has no line when there is nothing to say", () => {
    expect(heroSentence("drivers", open({ next: null }))).toBeNull();
    expect(heroSentence("drivers", open({ earliest: null }, false))).toBeNull();
  });

  it("reads the captured payloads", () => {
    expect(heroSentence("drivers", CLINCH_2026.afterRound19.drivers!)).toEqual({
      strong: "Provisionally clinched in Mexico City",
      rest: " with four races to spare: 119 points clear, and only 100 left to win.",
    });
    expect(heroSentence("constructors", CLINCH_2026.afterRound19.constructors!)?.rest).toBe(
      "Mercedes clinch in São Paulo if they outscore Ferrari by 3.",
    );
    expect(heroSentence("constructors", CLINCH_2026.afterRound20.constructors!)?.strong).toBe("Clinched in São Paulo");
  });
});

describe("clinchAside", () => {
  it("says where a title was clinched, provisionally or not", () => {
    const title = open({ decided: true, next: null, earliest: null, decided_at: decided({}) });
    expect(clinchAside("drivers", title)).toBe("Kimi Antonelli clinched in Mexico City");
    expect(clinchAside("drivers", { ...title, decided_at: decided({ provisional: true }) })).toBe(
      "Kimi Antonelli provisionally clinched in Mexico City",
    );
  });

  it("says a title is clinched when the round is unknown", () => {
    const title = open({
      decided: true,
      next: null,
      earliest: null,
      leader: { name: "Mercedes", code: null, team: "Mercedes", points: 1 },
    });
    expect(clinchAside("constructors", title)).toBe("Mercedes have clinched the title");
  });

  it("says where an open title can be clinched", () => {
    expect(clinchAside("drivers", open())).toBe("Kimi Antonelli can clinch in Mexico City");
    expect(clinchAside("drivers", open({}, false))).toBe("Kimi Antonelli can clinch in Las Vegas at the earliest");
    expect(clinchAside("constructors", CLINCH_2026.afterRound20.constructors!)).toBe("Mercedes clinched in São Paulo");
    expect(clinchAside("constructors", CLINCH_2026.afterRound19.constructors!)).toBe(
      "Mercedes can clinch in São Paulo",
    );
  });

  it("is empty when nothing can be said", () => {
    expect(clinchAside("drivers", open({ next: null, earliest: null }))).toBeNull();
  });
});

describe("stayInItSentence", () => {
  it("tells a rival what keeps them in it", () => {
    expect(stayInItSentence("constructors", { name: "Mercedes", code: null }, need("Ferrari", 3))).toBe(
      "Ferrari stay in it unless Mercedes outscore them by 3 or more.",
    );
    expect(stayInItSentence("drivers", ANT, need("George Russell", 24, true, "RUS"))).toBe(
      "George Russell stays in it unless Kimi Antonelli outscores them by 24 or more (23 goes to count-back).",
    );
  });

  it("tells a rival what they must do when the leader is already ahead of them", () => {
    expect(stayInItSentence("drivers", ANT, RUS)).toBe(
      "George Russell must outscore Kimi Antonelli by 24 or more to stay in it.",
    );
    expect(stayInItSentence("drivers", NOR, need("Max Verstappen", -11, true, "VER"))).toBe(
      "Max Verstappen must outscore Lando Norris by 13 or more to stay in it (12 goes to count-back).",
    );
  });
});

describe("entrantClause", () => {
  it("names a champion's clinch", () => {
    const title = CLINCH_2026.afterRound20.constructors!;
    expect(entrantClause("constructors", title, { name: "Mercedes" })).toBe(
      "Clinched in São Paulo with three races to spare.",
    );
    const drivers = CLINCH_2026.afterRound19.drivers!;
    expect(entrantClause("drivers", drivers, { name: "Kimi Antonelli", code: "ANT" })).toBe(
      "Provisionally clinched in Mexico City with four races to spare.",
    );
    const last = open({
      decided: true,
      next: null,
      earliest: null,
      decided_at: decided({ races_to_spare: 0, sprints_to_spare: 0 }),
    });
    expect(entrantClause("drivers", last, ANT)).toBe("Clinched in Mexico City at the final round.");
  });

  it("says nothing about a champion whose clinch round is unknown", () => {
    expect(entrantClause("drivers", open({ decided: true, next: null }), ANT)).toBeNull();
  });

  it("says where an open leader can clinch", () => {
    expect(entrantClause("drivers", open(), ANT)).toBe("Can clinch in Mexico City.");
    expect(entrantClause("drivers", open({}, false), ANT)).toBe("Can clinch in Las Vegas at the earliest.");
    expect(entrantClause("drivers", open({ earliest: null }, false), ANT)).toBeNull();
  });

  it("tells a rival what keeps them in it, or that they are still in the fight", () => {
    const title = CLINCH_2026.afterRound19.constructors!;
    expect(entrantClause("constructors", title, { name: "Ferrari" })).toBe(
      "Ferrari stay in it unless Mercedes outscore them by 3 or more.",
    );
    const far = open({}, true, [need("George Russell", 40, false, "RUS")]);
    expect(entrantClause("drivers", far, { name: "George Russell", code: "RUS" })).toBe("Still in the title fight.");
  });

  it("says nothing about everyone else", () => {
    expect(entrantClause("drivers", open(), { name: "Max Verstappen", code: "VER" })).toBeNull();
    expect(entrantClause("drivers", open({ next: null }), { name: "George Russell", code: "RUS" })).toBeNull();
  });
});

describe("contenderName", () => {
  it("prints a driver's full name and a team's f1db name", () => {
    expect(contenderName("drivers", "Kimi Antonelli", "ANT")).toBe("Kimi Antonelli");
    expect(contenderName("constructors", "Mercedes")).toBe("Mercedes");
  });
});
