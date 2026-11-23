import { describe, expect, it } from "vitest";

import { DEBRIEF_RADIO_R19 } from "@/test/fixtures/debrief";

import {
  attachedCount,
  circuitClock,
  clipCount,
  lapGroups,
  mmss,
  MOMENT_TAG,
  moreSummary,
  offsetLabel,
  pauseLabel,
  playLabel,
  RACE_TITLE,
  radioTitle,
  timesNote,
} from "./radioModel";

import type { RadioClip } from "./debriefTypes";

const [START, , SC] = DEBRIEF_RADIO_R19.moments;
const HIR = START.clips[0];
const LEC = SC.clips[0];

describe("radioModel", () => {
  it("counts the attached clips and titles the section from the data", () => {
    expect(attachedCount(DEBRIEF_RADIO_R19)).toBe(14);
    expect(radioTitle(DEBRIEF_RADIO_R19)).toBe("14 of 27 clips came within a lap of a race moment");
    expect(radioTitle({ ...DEBRIEF_RADIO_R19, total: 1 })).toBe("14 of 1 clip came within a lap of a race moment");
  });

  it("reads the circuit's wall clock from the UTC string", () => {
    expect(circuitClock(HIR.at, -360)).toBe("13:55:24");
    expect(circuitClock(LEC.at, -360)).toBe("15:02:27");
    expect(circuitClock(HIR.at, null)).toBe("19:55:24");
  });

  it("labels the offset and the note", () => {
    expect(offsetLabel(-360)).toBe("UTC−6");
    expect(offsetLabel(330)).toBe("UTC+5:30");
    expect(offsetLabel(0)).toBe("UTC");
    expect(timesNote(-360)).toBe("times are local (UTC−6)");
    expect(timesNote(null)).toBe("times in UTC");
  });

  it("tags every moment kind and titles the race-wide ones", () => {
    expect(MOMENT_TAG).toEqual({
      start: "Start",
      safety_car: "Safety Car",
      safety_car_in: "Safety Car",
      vsc: "VSC",
      vsc_ending: "VSC",
      red_flag: "Red flag",
      chequered: "Flag",
      stop: "Stop",
      penalty: "Penalty",
      incident: "Incident",
      retirement: "DNF",
    });
    expect(RACE_TITLE).toEqual({
      start: "Formation lap and start",
      safety_car: "Safety Car deployed",
      safety_car_in: "Safety Car in",
      vsc: "Virtual Safety Car deployed",
      vsc_ending: "Virtual Safety Car ending",
      red_flag: "Red flag · race suspended",
      chequered: "Chequered flag",
    });
  });

  it("counts clips in singular and plural", () => {
    expect(clipCount(1)).toBe("1 clip");
    expect(clipCount(3)).toBe("3 clips");
    expect(moreSummary(13)).toBe("13 more clips, not within a lap of a race moment");
    expect(moreSummary(1)).toBe("1 more clip, not within a lap of a race moment");
  });

  it("groups the unattached clips by lap in first-seen order", () => {
    const groups = lapGroups(DEBRIEF_RADIO_R19.unattached);

    expect(groups.map((group) => group.lap)).toEqual([14, 15, 23, 24, 29, 30, 32, 38, 52, 54, 56]);
    expect(groups.find((group) => group.lap === 15)?.clips).toHaveLength(2);
  });

  it("labels play and pause for a screen reader, and never calls the pre-start a lap", () => {
    const early: RadioClip = { ...HIR, driver_name: "Lando Norris", at: "2026-11-01T19:59:28.007000+00:00" };

    expect(playLabel(early, -360)).toBe("Play Lando Norris team radio, before the start, 13:59:28");
    expect(playLabel(LEC, -360)).toBe("Play Charles Leclerc team radio, lap 43, 15:02:27");
    expect(pauseLabel(LEC)).toBe("Pause Charles Leclerc team radio");
  });

  it("formats elapsed seconds as m:ss", () => {
    expect(mmss(4)).toBe("0:04");
    expect(mmss(65)).toBe("1:05");
  });
});
