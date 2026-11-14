import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { MobileNav } from "./MobileNav";

vi.mock("./RaceStatusChip", () => ({ RaceStatusChip: () => <span>Race status</span> }));

function setup(pathname = "/race-control/grand-prix") {
  const user = userEvent.setup();
  const view = render(<MobileNav pathname={pathname} />);
  return { user, ...view, menu: screen.getByRole("button", { name: "Menu" }) };
}

async function openMenu(pathname?: string) {
  const ctx = setup(pathname);
  await ctx.user.click(ctx.menu);
  return { ...ctx, dialog: screen.getByRole("dialog", { name: "Site menu" }) };
}

const root = document.documentElement;

describe("MobileNav", () => {
  it("is a MENU button below xl, with nothing open", () => {
    const { menu } = setup();

    expect(menu).toHaveClass("xl:hidden", "font-mono", "uppercase");
    expect(menu).toHaveAttribute("aria-haspopup", "dialog");
    expect(menu).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("opens a modal menu of every section, focus on Close, the page behind it held still", async () => {
    const { menu, dialog } = await openMenu();

    expect(menu).toHaveAttribute("aria-expanded", "true");
    expect(dialog).toHaveAttribute("aria-modal", "true");
    expect(within(dialog).getByRole("button", { name: "Close" })).toHaveFocus();
    expect(root.style.overflow).toBe("hidden");

    const links = within(within(dialog).getByRole("navigation", { name: "Main" })).getAllByRole("link");
    expect(links.map((el) => el.textContent)).toEqual([
      "01Race Control",
      "02Grand Prix",
      "03Telemetry",
      "04Standings",
      "05Teams",
      "06Power Units",
      "07AI Engineer",
      "08Champions",
      "09Debriefs",
      "10Rulebook",
    ]);
    expect(within(dialog).getByText("More")).toBeInTheDocument();
    expect(within(dialog).getByRole("link", { name: "F1 AI home" })).toBeInTheDocument();
  });

  it("marks the current section: aria-current, the red numeral and the primary tone", async () => {
    const { dialog } = await openMenu("/race-control/grand-prix");

    const current = within(dialog).getByRole("link", { name: /Grand Prix/ });
    expect(current).toHaveAttribute("aria-current", "page");
    expect(within(current).getByText("02")).toHaveClass("text-rc-red-text");
    expect(within(current).getByText("Grand Prix")).toHaveClass("text-rc-ink");

    const other = within(dialog).getByRole("link", { name: /Telemetry/ });
    expect(other).not.toHaveAttribute("aria-current");
    expect(within(other).getByText("03")).toHaveClass("text-rc-ink-3");
  });

  it("carries the race status on data routes, never on the static homepage", async () => {
    const { dialog, unmount } = await openMenu("/race-control/grand-prix");
    expect(within(dialog).getByText("Race status")).toBeInTheDocument();
    unmount();

    const home = await openMenu("/");
    expect(within(home.dialog).queryByText("Race status")).toBeNull();
  });

  it("closes on Escape or Close, handing focus back to MENU and the page its scroll", async () => {
    const { user, menu } = await openMenu();

    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(menu).toHaveFocus();
    expect(menu).toHaveAttribute("aria-expanded", "false");
    expect(root.style.overflow).toBe("");

    await user.click(menu);
    await user.click(screen.getByRole("button", { name: "Close" }));
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(menu).toHaveFocus();
  });

  it("keeps Tab inside the menu, both ways", async () => {
    const { user, dialog } = await openMenu();

    const home = within(dialog).getByRole("link", { name: "F1 AI home" });
    const last = within(dialog).getByRole("link", { name: /Rulebook/ });
    await user.tab({ shift: true });
    expect(home).toHaveFocus();
    await user.tab({ shift: true });
    expect(last).toHaveFocus();
    await user.tab();
    expect(home).toHaveFocus();
    await user.tab();
    expect(within(dialog).getByRole("button", { name: "Close" })).toHaveFocus();
  });

  it("ignores other keys", async () => {
    const { user } = await openMenu();

    await user.keyboard("a");
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  it("closes when a link is chosen, and on navigation", async () => {
    const { user, menu, dialog, rerender } = await openMenu();

    // Following the link is the router's job, and jsdom cannot navigate: cancel it before it starts.
    document.addEventListener("click", (event) => event.preventDefault(), { capture: true, once: true });
    await user.click(within(dialog).getByRole("link", { name: /Telemetry/ }));
    expect(screen.queryByRole("dialog")).toBeNull();

    await user.click(menu);
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    rerender(<MobileNav pathname="/race-control/telemetry" />);
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(root.style.overflow).toBe("");
  });
});
