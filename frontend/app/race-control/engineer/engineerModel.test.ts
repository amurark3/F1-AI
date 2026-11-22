import { describe, expect, it } from "vitest";

import type { OverviewShell } from "@/app/race-control/components/CommandCenterPanels";
import type { TableStakes } from "@/app/race-control/weekend/weekendTypes";
import { OVERVIEW_SEGMENTS_2026 } from "@/test/fixtures";

import {
  answerHeader,
  historyGroups,
  parseChatStream,
  starterPrompts,
  toAnswerData,
  type AnswerData,
  type Chat,
} from "./engineerModel";

/** The 2026 title fight for second after round 19 (the mockup's chart); the leader is out of reach. */
const CHART = {
  kind: "reach",
  title: "5 drivers can still finish second · points after round 19 → most possible",
  championship: "drivers",
  year: 2026,
  rows: [
    { key: "VER", name: "Max Verstappen", team: "Red Bull", points: 261, max: 361 },
    { key: "HAM", name: "Lewis Hamilton", team: "Ferrari", points: 259, max: 359 },
  ],
};
const DATA = {
  subject: "2026 standings after round 19",
  sources: ["f1db v2026.19.0 · standings after R19"],
  charts: [CHART],
};

describe("toAnswerData", () => {
  it("keeps a well-formed payload", () => {
    expect(toAnswerData(DATA)).toEqual(DATA);
  });

  it("drops what is malformed and keeps the rest", () => {
    const parsed = toAnswerData({
      subject: 7,
      sources: ["a", 3, "b"],
      charts: [
        CHART,
        { ...CHART, kind: "bars" },
        { ...CHART, championship: "pilots" },
        { ...CHART, year: "2026" },
        { ...CHART, rows: "none" },
        { ...CHART, rows: [{ key: "VER", name: "Max", team: "Red Bull", points: "261", max: 361 }] },
        { ...CHART, rows: [{ key: 1, name: "Max", team: "Red Bull", points: 261, max: 361 }] },
        { ...CHART, rows: [null] },
        null,
      ],
    });

    expect(parsed).toEqual({ subject: null, sources: ["a", "b"], charts: [CHART] });
  });

  it("reads missing lists as empty", () => {
    expect(toAnswerData({})).toEqual({ subject: null, sources: [], charts: [] });
  });

  it.each([null, "text", 4, ["x"]])("is null for %j", (value) => {
    expect(toAnswerData(value)).toBeNull();
  });
});

describe("parseChatStream", () => {
  const block = `[ANSWER_DATA]${JSON.stringify(DATA)}[/ANSWER_DATA]`;

  it("strips every marker from the answer, and reads the data and the last tool", () => {
    const raw = `[TOOL_START]Get Driver Standings[/TOOL_START][TOOL_END]Get Driver Standings[/TOOL_END]${block}Hello.`;

    expect(parseChatStream(raw, true)).toEqual({ content: "Hello.", toolStatus: null, data: DATA });
  });

  it("reports the tool still running", () => {
    const raw = "[TOOL_START]A[/TOOL_START][TOOL_END]A[/TOOL_END][TOOL_START]B[/TOOL_START]";

    expect(parseChatStream(raw, false).toolStatus).toBe("B");
  });

  it("takes the last data block, and null for bad JSON or a non-object", () => {
    const other = { ...DATA, subject: "later" };
    const two = `${block}[ANSWER_DATA]${JSON.stringify(other)}[/ANSWER_DATA]x`;

    expect(parseChatStream(two, true).data?.subject).toBe("later");
    expect(parseChatStream("[ANSWER_DATA]{oops[/ANSWER_DATA]x", true).data).toBeNull();
    expect(parseChatStream("[ANSWER_DATA]3[/ANSWER_DATA]x", true).data).toBeNull();
  });

  it("never loses a marker split across two chunks", () => {
    const first = `[TOOL_START]Get Driver Stand`;
    const raw = `${first}ings[/TOOL_START]${block.slice(0, 40)}`;

    expect(parseChatStream(first, false)).toEqual({ content: "", toolStatus: null, data: null });
    expect(parseChatStream(raw, false)).toEqual({ content: "", toolStatus: "Get Driver Standings", data: null });
    expect(parseChatStream(`${raw}${block.slice(40)}Hi`, false).data).toEqual(DATA);
  });

  it("cuts a marker still arriving from the text, but only while the stream is open", () => {
    expect(parseChatStream("Hello [TOOL_ST", false).content).toBe("Hello ");
    expect(parseChatStream("Hello [", false).content).toBe("Hello ");
    expect(parseChatStream("Hello [TOOL_START]x", false).content).toBe("Hello ");
    expect(parseChatStream(`Hi [ANSWER_DATA]{"sources": ["a"`, false).content).toBe("Hi ");
    expect(parseChatStream("Hello [TOOL_ST", true).content).toBe("Hello [TOOL_ST");
  });

  it("leaves brackets that start no marker, and trims once done", () => {
    expect(parseChatStream("Pole [1] and [NOR", false).content).toBe("Pole [1] and [NOR");
    expect(parseChatStream("  Hello \n", true).content).toBe("Hello");
    expect(parseChatStream("  Hello ", false).content).toBe("  Hello ");
  });
});

describe("historyGroups", () => {
  const NOW = new Date(2026, 10, 22, 15, 0).getTime();
  const chat = (id: string, updatedAt: number): Chat => ({ id, title: id, updatedAt, messages: [] });

  it("groups threads as Today and Earlier, newest first", () => {
    const groups = historyGroups(
      [chat("old", NOW - 3 * 86_400_000), chat("morning", NOW - 3_600_000), chat("noon", NOW - 1_800_000)],
      NOW,
    );

    expect(groups.map((group) => [group.label, group.entries.map((entry) => entry.chat.id)])).toEqual([
      ["Today", ["noon", "morning"]],
      ["Earlier", ["old"]],
    ]);
  });

  it("leaves an empty group out", () => {
    expect(historyGroups([chat("a", NOW)], NOW).map((group) => group.label)).toEqual(["Today"]);
    expect(historyGroups([chat("a", NOW - 5 * 86_400_000)], NOW).map((group) => group.label)).toEqual(["Earlier"]);
    expect(historyGroups([], NOW)).toEqual([]);
  });

  it("places the deleted thread where its time puts it, marked", () => {
    const groups = historyGroups([chat("a", NOW), chat("c", NOW - 20_000)], NOW, chat("b", NOW - 10_000));

    expect(groups[0].entries.map((entry) => [entry.chat.id, entry.deleted])).toEqual([
      ["a", false],
      ["b", true],
      ["c", false],
    ]);
  });
});

describe("answerHeader", () => {
  it("names the engineer, and what the answer read", () => {
    expect(answerHeader(null)).toBe("Engineer");
    expect(answerHeader(undefined)).toBe("Engineer");
    expect(answerHeader("")).toBe("Engineer");
    expect(answerHeader("2026 calendar")).toBe("Engineer · 2026 calendar");
  });
});

describe("starterPrompts", () => {
  const SHELL = OVERVIEW_SEGMENTS_2026.shell as unknown as OverviewShell;
  const RULES = { kicker: "Rules", text: "When does a parc fermé change mean a pit-lane start?" };

  function stakesWith(changes: { drivers?: Partial<TableStakes>; constructors?: Partial<TableStakes> }): OverviewShell {
    const stakes = SHELL.stakes;
    if (!stakes?.drivers || !stakes.constructors) throw new Error("the fixture has both tables");
    return {
      ...SHELL,
      stakes: {
        ...stakes,
        drivers: { ...stakes.drivers, ...changes.drivers },
        constructors: { ...stakes.constructors, ...changes.constructors },
      },
    };
  }

  it("computes the four prompts and two chips from the São Paulo shell", () => {
    expect(starterPrompts(SHELL)).toEqual({
      prompts: [
        { kicker: "Drivers' championship", text: "Who can still finish second in the drivers' championship?" },
        { kicker: "Constructors' championship", text: "Can Ferrari still beat Mercedes to the constructors' title?" },
        { kicker: "Round 20 · Upcoming", text: "Who does the model favour for the São Paulo Grand Prix?" },
        RULES,
      ],
      sources: ["f1db v2026.19.0 · standings after R19", "calendar · round 20"],
    });
  });

  it("asks about the one rival still alive in the drivers' title, or the several", () => {
    const contenders = SHELL.stakes?.drivers?.contenders.map((c) => ({ ...c, alive: c.position <= 2 })) ?? [];
    const open = (rivals: number) => ({ decided: false, rivals_alive: rivals, contenders });
    const one = starterPrompts(stakesWith({ drivers: open(1) })).prompts[0].text;
    const several = starterPrompts(stakesWith({ drivers: open(2) })).prompts[0].text;

    expect(one).toBe("Can Max Verstappen still catch Kimi Antonelli?");
    expect(several).toBe("Who can still catch Kimi Antonelli for the drivers' title?");
  });

  it("asks about the constructors' title when decided, or with several rivals", () => {
    const decided = starterPrompts(stakesWith({ constructors: { decided: true, rivals_alive: 0 } }));
    const several = starterPrompts(stakesWith({ constructors: { rivals_alive: 3 } }));

    expect(decided.prompts[1].text).toBe("Who can still finish second in the constructors' championship?");
    expect(several.prompts[1].text).toBe("Who can still beat Mercedes to the constructors' title?");
  });

  it("falls back to the several-rivals question when the one rival is not named", () => {
    const shell = stakesWith({ drivers: { decided: false, rivals_alive: 1, contenders: [] } });

    expect(starterPrompts(shell).prompts[0].text).toBe("Who can still catch Kimi Antonelli for the drivers' title?");
  });

  it.each([
    ["in_progress", "Round 20 · Weekend live", "What has happened so far at the São Paulo Grand Prix?"],
    ["completed", "Round 20 · Completed", "What decided the São Paulo Grand Prix?"],
  ])("words a %s weekend", (status, kicker, text) => {
    const race = { ...SHELL.race, status } as OverviewShell["race"];

    expect(starterPrompts({ ...SHELL, race }).prompts[2]).toEqual({ kicker, text });
  });

  it("leaves out a weekend in any other status", () => {
    const race = { ...SHELL.race, status: "cancelled" } as OverviewShell["race"];
    const { prompts, sources } = starterPrompts({ ...SHELL, race });

    expect(prompts).toHaveLength(3);
    expect(prompts.at(-1)).toEqual(RULES);
    expect(sources).toContain("calendar · round 20");
  });

  it("says a provisional table is, and names a base with no version", () => {
    const stakes = SHELL.stakes;
    if (!stakes) throw new Error("fixture has stakes");
    const provisional = { ...stakes, provisional: true };
    const unversioned = { ...stakes, sources: [{ source: "f1db", role: "base" as const, through_round: 19 }] };

    expect(starterPrompts({ ...SHELL, stakes: provisional }).sources[0]).toBe(
      "f1db v2026.19.0 · standings after R19 · provisional",
    );
    expect(starterPrompts({ ...SHELL, stakes: unversioned }).sources[0]).toBe("f1db · standings after R19");
  });

  it("names no standings chip for a table that holds no round", () => {
    const stakes = SHELL.stakes;
    if (!stakes) throw new Error("fixture has stakes");

    expect(starterPrompts({ ...SHELL, stakes: { ...stakes, as_of_round: null } }).sources).toEqual([
      "calendar · round 20",
    ]);
  });

  it("is the rules question alone, with no chips, without a shell or with an empty one", () => {
    expect(starterPrompts(undefined)).toEqual({ prompts: [RULES], sources: [] });
    expect(starterPrompts({})).toEqual({ prompts: [RULES], sources: [] });
    expect(starterPrompts({ race: null })).toEqual({ prompts: [RULES], sources: [] });
  });
});

describe("the fixture", () => {
  it("is typed as the answer data the stream sends", () => {
    const data: AnswerData | null = toAnswerData(DATA);
    expect(data?.charts[0].rows).toHaveLength(2);
  });
});
