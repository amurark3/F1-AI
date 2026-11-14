import { render, screen, within } from "@testing-library/react";
import { usePathname } from "next/navigation";
import { describe, expect, it, vi } from "vitest";

import { AppShell } from "./AppShell";

vi.mock("next/navigation", () => ({ usePathname: vi.fn() }));
vi.mock("./RaceStatusChip", () => ({ RaceStatusChip: () => <span>Race status</span> }));

function renderAt(pathname: string) {
  vi.mocked(usePathname).mockReturnValue(pathname);
  return render(
    <AppShell>
      <p>Page content</p>
    </AppShell>,
  );
}

const main = () => screen.getByRole("main");
const footerNav = () => within(screen.getByRole("contentinfo")).getByRole("navigation", { name: "Footer" });

describe("AppShell", () => {
  it("opens with a skip link to the page, then the one top bar", () => {
    renderAt("/race-control/telemetry");

    const skip = screen.getByRole("link", { name: "Skip to content" });
    expect(skip).toHaveAttribute("href", "#main");
    expect(skip).toHaveClass("sr-only", "focus:not-sr-only");
    expect(screen.getAllByRole("banner")).toHaveLength(1);
    expect(within(screen.getByRole("banner")).getByRole("link", { name: "Telemetry" })).toHaveAttribute(
      "aria-current",
      "page",
    );
    expect(main()).toHaveAttribute("id", "main");
    expect(main()).toHaveTextContent("Page content");
  });

  it("frames a data screen in the page wrap, over the footer", () => {
    const { container } = renderAt("/race-control/drivers/lewis-hamilton");

    expect(container.firstElementChild).toHaveClass("flex", "flex-col", "min-h-dvh");
    expect(main()).toHaveClass("max-w-7xl", "px-5", "lg:px-8", "pt-8", "pb-24", "flex-1");
    expect(footerNav()).toBeInTheDocument();
  });

  it("leaves the homepage bare, over the same footer", () => {
    renderAt("/");

    expect(main()).toHaveClass("flex-1");
    expect(main()).not.toHaveClass("max-w-7xl");
    expect(footerNav()).toBeInTheDocument();
  });

  it("gives the AI Engineer the viewport under the bar, with no footer", () => {
    const { container } = renderAt("/race-control/engineer");

    expect(container.firstElementChild).toHaveClass("h-dvh");
    expect(main()).toHaveClass("flex", "min-h-0", "flex-1");
    expect(main()).not.toHaveClass("max-w-7xl");
    expect(screen.queryByRole("contentinfo")).toBeNull();
  });
});
