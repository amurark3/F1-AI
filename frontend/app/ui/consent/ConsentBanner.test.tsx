import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type * as StoreModule from "./analyticsConsent";
import type { ConsentBanner as Banner } from "./ConsentBanner";

const KEY = "f1ai:analytics-consent";

let store: typeof StoreModule;
let ConsentBanner: typeof Banner;

beforeEach(async () => {
  localStorage.clear();
  vi.resetModules();
  store = await import("./analyticsConsent");
  ({ ConsentBanner } = await import("./ConsentBanner"));
});

const banner = () => screen.queryByRole("region", { name: "Analytics cookies" });

describe("ConsentBanner", () => {
  it("asks a first-time visitor, with Allow and Decline styled the same", () => {
    render(<ConsentBanner />);

    expect(banner()).toHaveTextContent("May we use Google Analytics");
    const decline = screen.getByRole("button", { name: "Decline" });
    const allow = screen.getByRole("button", { name: "Allow" });
    expect(decline.className).toBe(allow.className);
  });

  it.each([
    ["Allow", "granted"],
    ["Decline", "denied"],
  ])("closes and remembers the answer after %s", async (label, stored) => {
    render(<ConsentBanner />);

    await userEvent.click(screen.getByRole("button", { name: label }));

    expect(banner()).toBeNull();
    expect(localStorage.getItem(KEY)).toBe(stored);
  });

  it("stays away for a visitor who already answered, until Cookie settings brings it back", () => {
    localStorage.setItem(KEY, "denied");
    render(<ConsentBanner />);
    expect(banner()).toBeNull();

    act(() => store.reopenConsent());

    expect(banner()).not.toBeNull();
  });
});
