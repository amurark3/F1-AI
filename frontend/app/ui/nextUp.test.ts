import { describe, expect, it } from "vitest";

import { nextUp } from "./nextUp";

/** A sprint weekend, listed out of order as a payload may send it. */
const SESSIONS = {
  Race: "2026-11-08T17:00:00Z",
  "Sprint Qualifying": "2026-11-06T18:30:00Z",
  "Practice 1": "2026-11-06T14:30:00Z",
  Sprint: "2026-11-07T14:00:00Z",
};

const at = (iso: string) => new Date(iso).getTime();

describe("nextUp", () => {
  it("points at the first session before the weekend starts", () => {
    expect(nextUp(SESSIONS, at("2026-11-01T00:00:00Z"))).toEqual({
      name: "Practice 1",
      startsAt: "2026-11-06T14:30:00Z",
      live: false,
    });
  });

  it("calls a session live from its start until its default hour is up", () => {
    expect(nextUp(SESSIONS, at("2026-11-06T14:30:00Z"))).toMatchObject({ name: "Practice 1", live: true });
    expect(nextUp(SESSIONS, at("2026-11-06T15:29:59Z"))).toMatchObject({ name: "Practice 1", live: true });
    expect(nextUp(SESSIONS, at("2026-11-06T15:30:00Z"))).toMatchObject({ name: "Sprint Qualifying", live: false });
  });

  it("gives sprint qualifying 45 minutes and the race two hours", () => {
    expect(nextUp(SESSIONS, at("2026-11-06T19:14:00Z"))).toMatchObject({ name: "Sprint Qualifying", live: true });
    expect(nextUp(SESSIONS, at("2026-11-06T19:15:00Z"))).toMatchObject({ name: "Sprint", live: false });
    expect(nextUp(SESSIONS, at("2026-11-08T18:59:00Z"))).toMatchObject({ name: "Race", live: true });
  });

  it("is null once the last session has ended", () => {
    expect(nextUp(SESSIONS, at("2026-11-08T19:00:00Z"))).toBeNull();
  });

  it("skips a session whose start time does not parse", () => {
    const sessions = { Sprint: "TBC", Race: "2026-11-08T17:00:00Z" };
    expect(nextUp(sessions, at("2026-11-01T00:00:00Z"))).toMatchObject({ name: "Race", live: false });
  });

  it("is null for a weekend with no sessions", () => {
    expect(nextUp({}, at("2026-11-01T00:00:00Z"))).toBeNull();
  });
});
