import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import RootLayout, { metadata } from "./layout";

import type { ReactNode } from "react";

vi.mock("next/font/google", () => {
  const face = ({ variable }: { variable: string }) => ({ variable: `face${variable}` });
  return { Geist: face, Geist_Mono: face, Barlow_Condensed: face };
});
vi.mock("@vercel/analytics/next", () => ({ Analytics: () => null }));
vi.mock("@vercel/speed-insights/next", () => ({ SpeedInsights: () => null }));
const consent = vi.hoisted(() => ({ GA_ID: null as string | null }));
vi.mock("./ui/consent/measurementId", () => consent);
vi.mock("./ui/consent/GoogleAnalytics", () => ({
  GoogleAnalytics: ({ id }: { id: string }) => <div data-testid="ga" data-id={id} />,
}));
vi.mock("./ui/consent/ConsentBanner", () => ({ ConsentBanner: () => <div data-testid="consent" /> }));
vi.mock("./components/ServerWarmingGate", () => ({
  default: ({ children }: { children: ReactNode }) => <div data-testid="warm-up">{children}</div>,
}));
vi.mock("./ui/shell/AppShell", () => ({
  AppShell: ({ children }: { children: ReactNode }) => <div data-testid="shell">{children}</div>,
}));

describe("RootLayout", () => {
  it("names the site", () => {
    expect(metadata.title).toBe("F1 AI");
  });

  it("puts the three faces' variables on <html>, so :root tokens that read them resolve", () => {
    render(
      <RootLayout>
        <p>Page</p>
      </RootLayout>,
    );

    expect(document.documentElement).toHaveAttribute("lang", "en");
    expect(document.documentElement).toHaveClass("face--font-geist-sans", "face--font-geist-mono", "face--font-barlow");
  });

  it("frames the page in the shell, inside the warm-up gate", () => {
    render(
      <RootLayout>
        <p>Page</p>
      </RootLayout>,
    );

    expect(screen.getByTestId("warm-up")).toContainElement(screen.getByTestId("shell"));
    expect(screen.getByTestId("shell")).toHaveTextContent("Page");
  });

  it("leaves Google Analytics and its banner out when no measurement ID is set", () => {
    consent.GA_ID = null;
    render(
      <RootLayout>
        <p>Page</p>
      </RootLayout>,
    );

    expect(screen.queryByTestId("ga")).toBeNull();
    expect(screen.queryByTestId("consent")).toBeNull();
  });

  it("adds Google Analytics for the configured property, with its consent banner", () => {
    consent.GA_ID = "G-AB12CD34EF";
    render(
      <RootLayout>
        <p>Page</p>
      </RootLayout>,
    );

    expect(screen.getByTestId("ga")).toHaveAttribute("data-id", "G-AB12CD34EF");
    expect(screen.getByTestId("consent")).toBeInTheDocument();
  });
});
