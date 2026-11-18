import { act, render, screen } from "@testing-library/react";
import { hydrateRoot } from "react-dom/client";
import { renderToString } from "react-dom/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type * as StoreModule from "./analyticsConsent";
import type { GoogleAnalytics as Loader } from "./GoogleAnalytics";
import type { ReactNode } from "react";

vi.mock("next/script", () => ({
  default: ({ src, id, children }: { src?: string; id?: string; children?: ReactNode }) => (
    <div data-testid="script" data-src={src} data-id={id}>
      {children}
    </div>
  ),
}));

const ID = "G-AB12CD34EF";
const KEY = "f1ai:analytics-consent";

let store: typeof StoreModule;
let GoogleAnalytics: typeof Loader;

beforeEach(async () => {
  localStorage.clear();
  document.cookie = "_ga=; max-age=0; path=/";
  vi.resetModules();
  store = await import("./analyticsConsent");
  ({ GoogleAnalytics } = await import("./GoogleAnalytics"));
});

const disabled = () => Reflect.get(window, `ga-disable-${ID}`) as unknown;

describe("GoogleAnalytics", () => {
  it("loads nothing before the visitor answers", () => {
    render(<GoogleAnalytics id={ID} />);

    expect(screen.queryAllByTestId("script")).toHaveLength(0);
    expect(disabled()).toBe(true);
  });

  it("loads gtag for this property once the visitor allows it", () => {
    render(<GoogleAnalytics id={ID} />);

    act(() => store.chooseAnalytics("granted"));

    const [loader, init] = screen.getAllByTestId("script");
    expect(loader).toHaveAttribute("data-src", `https://www.googletagmanager.com/gtag/js?id=${ID}`);
    expect(init).toHaveAttribute("data-id", "google-analytics");
    expect(init).toHaveTextContent(`gtag('config','${ID}')`);
    expect(disabled()).toBe(false);
  });

  it("stops the loaded tag and clears its cookies when the visitor declines later", () => {
    localStorage.setItem(KEY, "granted");
    render(<GoogleAnalytics id={ID} />);
    document.cookie = "_ga=GA1.1.123.456; path=/";

    act(() => store.chooseAnalytics("denied"));

    expect(screen.queryAllByTestId("script")).toHaveLength(0);
    expect(disabled()).toBe(true);
    expect(document.cookie).not.toContain("_ga=");
  });

  it("keeps a consenting visitor's cookies through hydration, when the answer is not yet known", async () => {
    const container = document.createElement("div");
    container.innerHTML = renderToString(<GoogleAnalytics id={ID} />);
    document.body.append(container);
    localStorage.setItem(KEY, "granted");
    document.cookie = "_ga=GA1.1.123.456; path=/";

    await act(async () => {
      hydrateRoot(container, <GoogleAnalytics id={ID} />);
      await Promise.resolve();
    });

    expect(document.cookie).toContain("_ga=GA1.1.123.456");
    expect(screen.getAllByTestId("script")).toHaveLength(2);
    container.remove();
  });
});
