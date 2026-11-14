import * as Sentry from "@sentry/nextjs";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import GlobalError from "./global-error";

vi.mock("@sentry/nextjs", () => ({ captureException: vi.fn() }));
vi.mock("next/font/google", () => {
  const face = ({ variable }: { variable: string }) => ({ variable: `face${variable}` });
  return { Geist: face, Geist_Mono: face, Barlow_Condensed: face };
});

function renderError(retry = vi.fn()) {
  const error = Object.assign(new Error("root layout failed"), { digest: "123" });
  render(<GlobalError error={error} retry={retry} />);
  return { error, retry };
}

describe("GlobalError", () => {
  it("reports the error to Sentry, since React swallows what a boundary catches", () => {
    const { error } = renderError();

    expect(Sentry.captureException).toHaveBeenCalledTimes(1);
    expect(Sentry.captureException).toHaveBeenCalledWith(error);
  });

  it("draws its own document with the site's three faces, since it replaces the root layout", () => {
    renderError();

    expect(document.documentElement).toHaveAttribute("lang", "en");
    expect(document.documentElement).toHaveClass("face--font-geist-sans", "face--font-geist-mono", "face--font-barlow");
    expect(document.title).toBe("Something went wrong · F1 AI");
  });

  it("says what happened in the page's one heading, under the lockup's way home", () => {
    renderError();

    const home = screen.getByRole("link", { name: "F1 AI home" });
    expect(home).toHaveAttribute("href", "/");
    expect(home.closest("header")).toHaveClass("border-b", "border-rc-line");
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Something went wrong");
    expect(screen.getByText("Error")).toBeInTheDocument();
  });

  it("tries the page again on request, or starts over from the homepage", () => {
    const { retry } = renderError();

    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(retry).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("link", { name: "Homepage" })).toHaveAttribute("href", "/");
  });
});
