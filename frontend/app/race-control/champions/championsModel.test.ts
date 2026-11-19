import { describe, expect, it } from "vitest";

import { CHAMPION_STATS } from "@/test/fixtures";
import { CHAMPIONS } from "@/test/fixtures/champions";

import {
  afterRound,
  cellLabel,
  decades,
  formatAge,
  heroCopy,
  leaderboardTitle,
  leaders,
  ordinal,
  sourceNote,
  stillToRun,
  titleState,
} from "./championsModel";

const SEASONS = CHAMPIONS.list.seasons ?? [];
const s2026 = SEASONS[0];
const s1957 = SEASONS.find((s) => s.season === 1957)!;
const drivers = CHAMPION_STATS.most_driver_titles ?? [];
const constructors = CHAMPION_STATS.most_constructor_titles ?? [];

describe("ordinal", () => {
  it.each([
    [1, "1st"],
    [2, "2nd"],
    [3, "3rd"],
    [4, "4th"],
    [11, "11th"],
    [12, "12th"],
    [13, "13th"],
    [21, "21st"],
    [22, "22nd"],
    [36, "36th"],
  ])("%i is %s", (n, text) => {
    expect(ordinal(n)).toBe(text);
  });
});

describe("small formats", () => {
  it("writes an age, a round, and the rounds left", () => {
    expect(formatAge({ years: 20, days: 68 })).toBe("20 y 68 d");
    expect(afterRound(s2026)).toBe("after round 20 of 23");
    expect(stillToRun(3)).toBe("3 rounds still to run");
    expect(stillToRun(1)).toBe("1 round still to run");
  });
});

describe("titleState", () => {
  it("is clinched while rounds remain, final after, open when undecided", () => {
    expect(titleState(s2026)).toBe("clinched");
    expect(titleState(s1957)).toBe("final");
    expect(titleState({ ...s2026, driver_champion: { ...s2026.driver_champion!, title_decided: false } })).toBe("open");
    expect(titleState({ ...s2026, driver_champion: null })).toBe("open");
  });
});

describe("heroCopy", () => {
  it("states Antonelli's records from the captured payload", () => {
    const copy = heroCopy(CHAMPIONS.latest);

    expect(copy.eyebrow).toBe("World Champions · 1950–2026");
    expect(copy.title).toBe("Antonelli joins the list");
    expect(copy.meta).toBe(
      "Kimi Antonelli clinched the 2026 title in Mexico City, the 36th different driver to become World Champion. 3 rounds still to run.",
    );
    expect(copy.facts).toEqual([
      { value: "20 y 68 d", caption: "Youngest champion ever · Vettel was 23 y 134 d in 2010" },
      { value: "1953", caption: "Italy's last champion before him · Alberto Ascari" },
      { value: "36th", caption: "different World Champion since 1950" },
    ]);
  });

  // Derived: Verstappen's fourth title, from the captured payload with its fields replaced.
  it("words a repeat champion who holds no record", () => {
    const copy = heroCopy({
      ...CHAMPIONS.latest,
      name: "Max Verstappen",
      last_name: "Verstappen",
      nationality: "Netherlands",
      title_number: 4,
      youngest_ever: false,
      previous_compatriot: null,
      round_count: 24,
      rounds_completed: 24,
      decided_at: { round: 22, date: "2024-11-23", place: null },
    });

    expect(copy.title).toBe("Verstappen makes it 4");
    expect(copy.meta).toBe("Max Verstappen clinched the 2026 title.");
    expect(copy.facts).toEqual([
      {
        value: "20 y 68 d",
        caption: "Age when the title was decided · the record is Vettel's 23 y 134 d in 2010",
      },
      { value: "1st", caption: "World Champion from Netherlands" },
      { value: "4th", caption: "World title for Verstappen" },
    ]);
  });

  it("leaves out the facts it has no data for", () => {
    const bare = heroCopy({ ...CHAMPIONS.latest, age: null, nationality: null, decided_at: null });
    expect(bare.facts).toHaveLength(1);
    expect(bare.meta).toMatch(/^Kimi Antonelli clinched the 2026 title,/);

    const noRecord = heroCopy({ ...CHAMPIONS.latest, previous_youngest: null });
    expect(noRecord.facts[0].caption).toBe("Age when the title was decided");
  });
});

describe("leaders and titles", () => {
  it("widens the cut to keep a tie whole", () => {
    expect(leaders(drivers)).toHaveLength(11);
    expect(leaders(constructors)).toHaveLength(9);
    expect(leaders(drivers.slice(0, 3))).toHaveLength(3);
    expect(leaders([])).toEqual([]);
  });

  it("computes each card's finding", () => {
    expect(leaderboardTitle(drivers, "drivers")).toBe("Hamilton and Schumacher, 7 each");
    expect(leaderboardTitle(constructors, "constructors")).toBe("Ferrari lead with 16");
    expect(leaderboardTitle(drivers.slice(2), "drivers")).toBe("Fangio leads with 5");
    expect(leaderboardTitle([], "drivers")).toBeNull();
  });
});

describe("the wall", () => {
  it("groups the 77 seasons into eight decades, newest first", () => {
    const groups = decades(SEASONS);

    expect(groups).toHaveLength(8);
    expect(groups[0]).toMatchObject({ label: "2020s" });
    expect(groups[0].seasons).toHaveLength(7);
    expect(groups[0].seasons.map((s) => s.season)).toEqual([2020, 2021, 2022, 2023, 2024, 2025, 2026]);
    expect(groups.at(-1)).toMatchObject({ label: "1950s" });
    expect(groups.at(-1)?.seasons.map((s) => s.season)).toEqual([
      1950, 1951, 1952, 1953, 1954, 1955, 1956, 1957, 1958, 1959,
    ]);
  });

  it("names each cell for a screen reader", () => {
    expect(cellLabel(s2026)).toBe(
      "2026: Kimi Antonelli, constructors' champion Mercedes, clinched with 3 rounds still to run",
    );
    expect(cellLabel(s1957)).toBe("1957: Juan Manuel Fangio");
    expect(cellLabel({ ...s2026, driver_champion: null })).toBe("2026: title still open");
    expect(cellLabel({ ...s2026, driver_champion: { ...s2026.driver_champion!, title_decided: false } })).toBe(
      "2026: title still open",
    );
  });

  it("writes the source note from the data", () => {
    expect(sourceNote(SEASONS)).toBe(
      "Source: f1db · 2026 after round 20 of 23 · constructors' title awarded from 1958",
    );
    expect(sourceNote([])).toBe("Source: f1db");
  });
});
