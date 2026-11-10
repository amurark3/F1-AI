import { describe, expect, it } from "vitest";

import {
  RESTARTING_REASON,
  UNREACHABLE_REASON,
  describeFailure,
  isRestarting,
  payloadError,
  sectionStatus,
  usableSeed,
} from "./sectionState";

describe("sectionStatus", () => {
  it("is ready with data and no failure", () => {
    expect(sectionStatus(true, false, false)).toBe("ready");
  });

  it("keeps data on a failed refresh: stale, never failed", () => {
    expect(sectionStatus(true, true, false)).toBe("stale");
    // A restart does not take the data away either.
    expect(sectionStatus(true, true, true)).toBe("stale");
  });

  it("fails only when there is no data and the server is up", () => {
    expect(sectionStatus(false, true, false)).toBe("failed");
  });

  it("waits while the first answer is out, or while the server restarts", () => {
    expect(sectionStatus(false, false, false)).toBe("pending");
    expect(sectionStatus(false, false, true)).toBe("pending");
    // A restarting backend is not a fault.
    expect(sectionStatus(false, true, true)).toBe("pending");
  });
});

describe("isRestarting", () => {
  it("counts a probe that has not answered yet and a warming server as restarting", () => {
    expect(isRestarting("unknown")).toBe(true);
    expect(isRestarting("warming")).toBe(true);
  });

  it("does not excuse a ready server or one the probe gave up on", () => {
    expect(isRestarting("ready")).toBe(false);
    expect(isRestarting("unreachable")).toBe(false);
  });
});

describe("describeFailure", () => {
  it("names a restart as a restart, whatever the error", () => {
    expect(describeFailure(new Error("Request failed: 500 Internal Server Error"), true)).toBe(RESTARTING_REASON);
    expect(RESTARTING_REASON).toBe("Waiting for the server to finish restarting.");
  });

  it("turns the browser's transport error into a sentence", () => {
    // fetch rejects with a TypeError whose text differs by browser.
    expect(describeFailure(new TypeError("Failed to fetch"), false)).toBe(UNREACHABLE_REASON);
    expect(describeFailure(new TypeError("Load failed"), false)).toBe("Could not reach the server.");
  });

  it("passes on any other message as it came", () => {
    expect(describeFailure(new Error("Request failed: 500 Internal Server Error"), false)).toBe(
      "Request failed: 500 Internal Server Error",
    );
  });
});

describe("payloadError", () => {
  it("reads the error a handled backend failure answers with", () => {
    expect(payloadError({ year: 2026, error: "Something went wrong loading this data. Try again shortly." })).toBe(
      "Something went wrong loading this data. Try again shortly.",
    );
  });

  it("finds no error in a good payload", () => {
    expect(payloadError({ year: 2026, race: null })).toBeNull();
    expect(payloadError({ error: null })).toBeNull();
    expect(payloadError({ error: "" })).toBeNull();
    expect(payloadError({ error: 500 })).toBeNull();
    expect(payloadError([{ error: "inside a list is data" }])).toBeNull();
    expect(payloadError(null)).toBeNull();
    expect(payloadError("text")).toBeNull();
  });
});

describe("usableSeed", () => {
  it("keeps a good server payload", () => {
    const seed = { year: 2026 };
    expect(usableSeed(seed)).toBe(seed);
  });

  it("drops a missing seed or one that carries an error, so the browser fetches", () => {
    expect(usableSeed(null)).toBeNull();
    expect(usableSeed(undefined)).toBeNull();
    expect(usableSeed({ year: 2026, error: "Something went wrong loading this data. Try again shortly." })).toBeNull();
  });
});
