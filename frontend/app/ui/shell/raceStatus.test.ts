import { describe, expect, it } from "vitest";

import { countdownText, raceStatus, type ShellRace } from "./raceStatus";

/** São Paulo 2026 (round 20), as the shell segment serves it. */
const SAO_PAULO: ShellRace = {
  round: 20,
  name: "São Paulo Grand Prix",
  status: "upcoming",
  sessions: {
    "Practice 1": "2026-11-06T15:30:00Z",
    "Practice 2": "2026-11-06T19:00:00Z",
    "Practice 3": "2026-11-07T14:30:00Z",
    Qualifying: "2026-11-07T18:00:00Z",
    Race: "2026-11-08T17:00:00Z",
  },
};

const at = (iso: string) => new Date(iso).getTime();

describe("raceStatus", () => {
  it("reads pre-race before the weekend, counting down to the first session", () => {
    expect(raceStatus(SAO_PAULO, at("2026-11-03T13:15:30Z"))).toEqual({
      phase: "pre-race",
      label: "R20 · Pre-race",
      event: "São Paulo Grand Prix",
      detail: "Practice 1 in 3d 02h 14m",
    });
  });

  it("stays pre-race between sessions, counting down to the next one", () => {
    const status = raceStatus({ ...SAO_PAULO, status: "in_progress" }, at("2026-11-08T14:00:00Z"));
    expect(status).toMatchObject({ phase: "pre-race", label: "R20 · Pre-race", detail: "Race in 3h 00m 00s" });
  });

  it("names the session on track while it runs", () => {
    expect(raceStatus({ ...SAO_PAULO, status: "in_progress" }, at("2026-11-07T18:20:00Z"))).toEqual({
      phase: "live",
      label: "R20 · Qualifying live",
      event: "São Paulo Grand Prix",
      detail: "Qualifying is on track",
    });
  });

  it("reads post-race once every session has run", () => {
    expect(raceStatus({ ...SAO_PAULO, status: "in_progress" }, at("2026-11-08T19:00:00Z"))).toEqual({
      phase: "post-race",
      label: "R20 · Post-race",
      event: "São Paulo Grand Prix",
      detail: "Every session has run",
    });
  });

  it("falls back on the weekend's status when no session has a time", () => {
    const untimed = { ...SAO_PAULO, sessions: {} };
    expect(raceStatus(untimed, at("2026-11-03T00:00:00Z"))).toMatchObject({ phase: "pre-race", detail: null });
    expect(raceStatus({ ...untimed, status: "completed" }, at("2026-11-03T00:00:00Z"))).toMatchObject({
      phase: "post-race",
      detail: "Every session has run",
    });
  });
});

describe("countdownText", () => {
  const now = at("2026-11-01T00:00:00Z");

  it("counts days, hours and minutes while a day or more is left", () => {
    expect(countdownText(at("2026-11-13T04:05:59Z"), now)).toBe("12d 04h 05m");
  });

  it("adds seconds inside the last day", () => {
    expect(countdownText(at("2026-11-01T09:08:07Z"), now)).toBe("9h 08m 07s");
  });

  it("drops the hours inside the last hour", () => {
    expect(countdownText(at("2026-11-01T00:04:09Z"), now)).toBe("4m 09s");
  });

  it("reads zero once the moment has passed", () => {
    expect(countdownText(at("2026-10-31T00:00:00Z"), now)).toBe("0m 00s");
  });
});
