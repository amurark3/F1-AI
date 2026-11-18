import { act, renderHook } from "@testing-library/react";
import { renderToString } from "react-dom/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type * as StoreModule from "./analyticsConsent";

type Store = typeof StoreModule;

const KEY = "f1ai:analytics-consent";

/** A fresh module per test: the answer and the reopened flag live in module state. */
let store: Store;

beforeEach(async () => {
  localStorage.clear();
  vi.resetModules();
  store = await import("./analyticsConsent");
});

/** Both hooks in one component, as the banner and the loader share the store. */
function useBoth() {
  return { consent: store.useAnalyticsConsent(), prompt: store.useConsentPrompt() };
}

describe("consent store", () => {
  it("asks a first-time visitor", () => {
    const { result } = renderHook(useBoth);

    expect(result.current).toEqual({ consent: "ask", prompt: true });
  });

  it("remembers an answer and closes the banner", () => {
    const { result } = renderHook(useBoth);

    act(() => store.chooseAnalytics("granted"));

    expect(result.current).toEqual({ consent: "granted", prompt: false });
    expect(localStorage.getItem(KEY)).toBe("granted");
  });

  it("reads a returning visitor's stored answer", () => {
    localStorage.setItem(KEY, "denied");

    const { result } = renderHook(useBoth);

    expect(result.current).toEqual({ consent: "denied", prompt: false });
  });

  it("asks again when the stored value is not an answer", () => {
    localStorage.setItem(KEY, "maybe");

    const { result } = renderHook(useBoth);

    expect(result.current.consent).toBe("ask");
  });

  it("reopens the banner without changing the answer until a new one is given", () => {
    localStorage.setItem(KEY, "granted");
    const { result } = renderHook(useBoth);

    act(() => store.reopenConsent());
    expect(result.current).toEqual({ consent: "granted", prompt: true });

    act(() => store.chooseAnalytics("denied"));
    expect(result.current).toEqual({ consent: "denied", prompt: false });
  });

  it("asks when storage is blocked, and keeps the answer for this page", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("SecurityError");
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("SecurityError");
    });
    const { result } = renderHook(useBoth);
    expect(result.current).toEqual({ consent: "ask", prompt: true });

    act(() => store.chooseAnalytics("denied"));

    expect(result.current).toEqual({ consent: "denied", prompt: false });
  });

  it("follows an answer given in another tab", () => {
    const { result } = renderHook(useBoth);
    act(() => store.chooseAnalytics("granted"));

    act(() => {
      localStorage.setItem(KEY, "denied");
      window.dispatchEvent(new StorageEvent("storage", { key: KEY }));
    });

    expect(result.current.consent).toBe("denied");
  });

  it("stops listening to other tabs once nothing reads the store", () => {
    const remove = vi.spyOn(window, "removeEventListener");
    const { unmount } = renderHook(useBoth);

    unmount();

    expect(remove).toHaveBeenCalledWith("storage", expect.any(Function));
  });

  it("knows nothing while server rendering, so no banner is in the HTML", () => {
    function Probe() {
      const { consent, prompt } = useBoth();
      return `${String(consent)}|${String(prompt)}`;
    }

    expect(renderToString(<Probe />)).toBe("null|false");
  });
});

describe("clearAnalyticsCookies", () => {
  it("expires gtag's cookies and leaves the rest", () => {
    document.cookie = "_ga=GA1.1.123.456; path=/";
    document.cookie = "_ga_AB12CD34EF=GS1.1.789; path=/";
    document.cookie = "keep=1; path=/";

    store.clearAnalyticsCookies();

    expect(document.cookie).toBe("keep=1");
    document.cookie = "keep=; max-age=0; path=/";
  });
});
