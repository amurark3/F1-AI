import { describe, expect, it } from "vitest";

import { RACE_RESULTS_2026 } from "@/test/fixtures";

import {
  penaltyLabel,
  positionLabel,
  provenanceNote,
  resultsTitle,
  stoppedLabel,
  timeLabel,
  type ResultRow,
  type SessionResult,
} from "./resultsModel";

const MEXICO = RACE_RESULTS_2026.mexicoCity.race!;

function row(code: string): ResultRow {
  const found = MEXICO.classification.find((candidate) => candidate.driver_code === code);
  if (!found) throw new Error(`${code} is not in the Mexico City fixture`);
  return found;
}

describe("positionLabel", () => {
  it("prints the place for a finisher and the status word for a car that retired", () => {
    expect(positionLabel(row("VER"))).toBe("1");
    expect(positionLabel(row("LIN"))).toBe("DNF");
  });
});

describe("stoppedLabel", () => {
  it("gives the reason and the laps completed", () => {
    expect(stoppedLabel(row("LIN"))).toBe("Collision · 58 laps");
  });

  it("says a single lap in the singular", () => {
    expect(stoppedLabel({ ...row("LIN"), laps: 1 })).toBe("Collision · 1 lap");
  });

  it("falls back to the status in words when the source gave neither", () => {
    const bare = { ...row("LIN"), reason: null, laps: null };
    expect(stoppedLabel(bare)).toBe("Retired");
    expect(stoppedLabel({ ...bare, status: "NC" })).toBe("Not classified");
    expect(stoppedLabel({ ...bare, status: "DNS", laps: 0 })).toBe("Did not start");
    expect(stoppedLabel({ ...bare, status: "DSQ" })).toBe("Disqualified");
  });
});

describe("timeLabel", () => {
  it("reads the winner's time, a gap, a lapped car's laps down, and a dash for nothing", () => {
    expect(timeLabel(row("VER"))).toBe("2:20:28.772");
    expect(timeLabel(row("HAM"))).toBe("+0.799");
    expect(timeLabel({ ...row("HAM"), gap: null, laps_down: 1 })).toBe("+1 lap");
    expect(timeLabel({ ...row("HAM"), gap: null, laps_down: 2 })).toBe("+2 laps");
    expect(timeLabel({ ...row("HAM"), gap: null })).toBe("—");
  });
});

describe("penaltyLabel", () => {
  it("names the penalty and where the car was on the road", () => {
    expect(penaltyLabel(row("PIA"))).toBe("incl. +10 s · P7 on the road");
    expect(penaltyLabel(row("GAS"))).toBe("incl. +30 s · P10 on the road");
  });

  it("leaves out the road place when the source does not give one, and is null with no penalty", () => {
    expect(penaltyLabel({ ...row("PIA"), road_position: null })).toBe("incl. +10 s");
    expect(penaltyLabel(row("HAM"))).toBeNull();
  });
});

describe("provenanceNote", () => {
  it("names f1db's release and says the classification is final", () => {
    expect(provenanceNote(MEXICO)).toBe(
      "Classification: f1db v2026.20.0, mirroring the FIA final classification · final",
    );
  });

  it("names the FIA's document when the classification is read from it", () => {
    const fromFia: SessionResult = {
      ...MEXICO,
      sources: [{ source: "fia-final-classification", role: "classification", document: 86 }],
    };
    expect(provenanceNote(fromFia)).toBe("Classification: FIA final classification, document 86 · final");
    expect(
      provenanceNote({ ...fromFia, sources: [{ source: "fia-final-classification", role: "classification" }] }),
    ).toBe("Classification: FIA final classification · final");
  });

  it("says provisional until the FIA's final lands, and prints a source it does not know as sent", () => {
    const provisional: SessionResult = {
      ...MEXICO,
      final: false,
      sources: [
        { source: "openf1-session-result", role: "classification" },
        { source: "f1db", role: "classification" },
        { source: "somewhere-new", role: "classification" },
      ],
    };
    expect(provenanceNote(provisional)).toBe(
      "Classification: OpenF1 session result, f1db, mirroring the FIA final classification, somewhere-new · provisional until the FIA final classification is published",
    );
  });
});

describe("resultsTitle", () => {
  it("is computed from the rows: the winner and how many cars retired", () => {
    expect(resultsTitle(MEXICO)).toBe("Max Verstappen wins; 5 cars retire");
  });

  it("handles one retirement, none, and no winner", () => {
    const [winner, ...rest] = MEXICO.classification;
    const one = { ...MEXICO, classification: [winner, ...rest.slice(0, 3), row("LIN")] };
    expect(resultsTitle(one)).toBe("Max Verstappen wins; 1 car retires");
    expect(resultsTitle({ ...MEXICO, classification: [winner] })).toBe("Max Verstappen wins");
    expect(resultsTitle({ ...MEXICO, classification: rest.slice(0, 2) })).toBe("Classification");
  });
});
