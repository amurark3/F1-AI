import { describe, expect, it } from "vitest";

import { RULEBOOK_2026 } from "@/test/fixtures/rulebook";

import {
  answerCopy,
  answerState,
  articleLabel,
  decisionBody,
  decisionLead,
  decisionMatch,
  markupParts,
  passageLabel,
  type RulebookSearched,
} from "./rulebookModel";

const FAILURE = (error: Error) => `failed: ${error.message}`;
const DECISION = RULEBOOK_2026.answered_ai.decisions.items[0];

describe("markupParts", () => {
  it("splits text, bold spans and source markers, in order", () => {
    expect(markupParts("See **Article B3.5.3** here [1][4] and on.")).toEqual([
      { kind: "text", value: "See " },
      { kind: "bold", value: "Article B3.5.3" },
      { kind: "text", value: " here " },
      { kind: "cite", value: "1" },
      { kind: "cite", value: "4" },
      { kind: "text", value: " and on." },
    ]);
  });

  it("returns plain text whole and nothing for nothing", () => {
    expect(markupParts("no markup")).toEqual([{ kind: "text", value: "no markup" }]);
    expect(markupParts("")).toEqual([]);
  });
});

describe("articleLabel", () => {
  it.each([
    [[], ""],
    [["B3.5.3"], "Article B3.5.3"],
    [["B3.5.3", "B3.5.4"], "Articles B3.5.3 and B3.5.4"],
    [["A1", "A2", "A3"], "Articles A1, A2 and A3"],
    [["A1", "A2", "A3", "A4", "A5"], "Articles A1, A2, A3 and 2 more"],
  ])("names %j as %j", (codes, label) => {
    expect(articleLabel(codes)).toBe(label);
  });
});

describe("the source labels", () => {
  const [passage] = RULEBOOK_2026.answered_ai.articles;

  it("says where a passage comes from, with its page and articles when it has them", () => {
    expect(passageLabel(passage, 2026)).toBe(
      "FIA 2026 F1 Regulations · Section B · Sporting · page 29 · Articles B3.5.3, B3.4.2, B3.4.3 and 1 more",
    );
    expect(passageLabel({ ...passage, page: null, codes: [] }, 2026)).toBe(
      "FIA 2026 F1 Regulations · Section B · Sporting",
    );
  });

  it("labels a decision up to its link, and by what it matched on after it", () => {
    expect(decisionLead(DECISION, 2026)).toBe("Stewards' decision · Mexico City Grand Prix 2026 · ");
    expect(decisionMatch(DECISION, "article")).toBe(" · cites B3.4.3, B3.5.3, B3.5.4");
    expect(decisionMatch({ ...DECISION, matched: ["pit", "lane"] }, "keyword")).toBe(" · keyword match: pit, lane");
  });

  it("quotes the decision, then the car, driver and session", () => {
    expect(decisionBody(DECISION)).toBe(
      "“Required to start the Race from the pit lane.” Car 30, Liam Lawson · Qualifying: Changes made during Parc Ferme.",
    );
    expect(decisionBody({ ...DECISION, driver: null, session: null })).toBe(
      "“Required to start the Race from the pit lane.” Car 30: Changes made during Parc Ferme.",
    );
  });
});

describe("answerCopy", () => {
  it("says an AI-written answer was checked against its sources", () => {
    const copy = answerCopy(RULEBOOK_2026.answered_ai);

    expect(copy.eyebrow).toBe("Answer · AI-written");
    expect(copy.note).toBe(
      "Written by AI from the sources below only; every article, document and car number in it was checked against them. Each decision links its FIA document",
    );
  });

  it("says why a computed answer is computed", () => {
    expect(answerCopy(RULEBOOK_2026.answered_computed)).toEqual({
      eyebrow: "Answer · computed",
      note: "The AI summary is unavailable just now, so this text is computed from the sources below. Each decision links its FIA document",
    });
    const failed: RulebookSearched = {
      ...RULEBOOK_2026.answered_computed,
      summary: { ...RULEBOOK_2026.answered_computed.summary, why: "check_failed" },
    };

    expect(answerCopy(failed).note).toBe(
      "The AI summary named something the sources don't hold, so this text is computed from the sources below instead. Each decision links its FIA document",
    );
  });

  it("labels keyword matches as such, whoever wrote the text", () => {
    const plain: RulebookSearched = {
      ...RULEBOOK_2026.keyword,
      summary: { ...RULEBOOK_2026.keyword.summary, why: null },
    };
    const written: RulebookSearched = {
      ...RULEBOOK_2026.keyword,
      summary: { ...RULEBOOK_2026.keyword.summary, written_by: "ai", why: null },
    };

    expect(answerCopy(plain)).toEqual({
      eyebrow: "Stewards' decisions · keyword matches",
      note: "Found by the question's words, not matched to an article of the regulations. Each decision links its FIA document",
    });
    expect(answerCopy(written).note).toBe(
      "Written by AI from the decisions below only; every article, document and car number in it was checked against them. Found by the question's words, not matched to an article of the regulations. Each decision links its FIA document",
    );
    expect(answerCopy(RULEBOOK_2026.keyword).note).toContain("computed from the decisions below.");
  });
});

describe("answerState", () => {
  it("is pending while a question is out, never showing the old answer", () => {
    expect(answerState(true, undefined, RULEBOOK_2026.answered_ai, FAILURE)).toEqual({
      status: "pending",
      reason: null,
    });
  });

  it("fails with the error described", () => {
    expect(answerState(false, new Error("HTTP 500"), undefined, FAILURE)).toEqual({
      status: "failed",
      reason: "failed: HTTP 500",
    });
  });

  it("fails with the server's reason when nothing could be searched", () => {
    const { reason } = RULEBOOK_2026.unavailable;

    expect(answerState(false, undefined, RULEBOOK_2026.unavailable, FAILURE)).toEqual({ status: "failed", reason });
  });

  it("is ready for an answered or keyword result, or before any data", () => {
    for (const data of [RULEBOOK_2026.answered_ai, RULEBOOK_2026.keyword, undefined]) {
      expect(answerState(false, undefined, data, FAILURE)).toEqual({ status: "ready", reason: null });
    }
  });
});
