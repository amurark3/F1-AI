import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it } from "vitest";

import { REFERENCE, type NavGroup } from "./navConfig";
import { NavMenu } from "./NavMenu";

function Menu({ pathname }: { pathname: string }) {
  const [open, setOpen] = useState<NavGroup["id"] | null>(null);
  return <NavMenu group={REFERENCE} pathname={pathname} open={open === REFERENCE.id} onOpen={setOpen} />;
}

function setup(pathname = "/race-control/telemetry") {
  const user = userEvent.setup();
  const view = render(
    <>
      <Menu pathname={pathname} />
      <button type="button">Elsewhere</button>
    </>,
  );
  return { user, ...view, trigger: screen.getByRole("button", { name: "Reference" }) };
}

const link = (name: string) => screen.getByRole("link", { name: new RegExp(`^${name}`) });

describe("NavMenu", () => {
  it("is a closed disclosure until pressed", () => {
    const { trigger } = setup();

    expect(trigger).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByRole("link")).toBeNull();
    expect(trigger).toHaveClass("text-rc-ink-3");
  });

  it("opens on a press to the two Reference screens, each with its line, and closes on another", async () => {
    const { user, trigger } = setup();

    await user.click(trigger);
    expect(trigger).toHaveAttribute("aria-expanded", "true");
    expect(trigger).toHaveClass("text-rc-ink");
    const panel = document.getElementById(trigger.getAttribute("aria-controls") ?? "");
    expect(panel).toBeVisible();
    expect(screen.getAllByRole("link").map((el) => el.getAttribute("href"))).toEqual([
      "/race-control/champions",
      "/race-control/rulebook",
    ]);
    expect(link("Champions")).toHaveTextContent("ChampionsEvery world champion since 1950");

    await user.click(trigger);
    expect(trigger).toHaveAttribute("aria-expanded", "false");
    expect(panel).not.toBeVisible();
  });

  it("closes on Escape and hands focus back to its button", async () => {
    const { user, trigger } = setup();

    await user.click(trigger);
    link("Champions").focus();
    await user.keyboard("{Escape}");
    expect(trigger).toHaveAttribute("aria-expanded", "false");
    expect(trigger).toHaveFocus();
  });

  it("closes on a press outside it, leaving focus where the press put it", async () => {
    const { user, trigger } = setup();

    await user.click(trigger);
    await user.click(screen.getByRole("button", { name: "Elsewhere" }));
    expect(trigger).toHaveAttribute("aria-expanded", "false");
    expect(screen.getByRole("button", { name: "Elsewhere" })).toHaveFocus();
  });

  it("closes when Tab leaves it, and stays open while focus moves inside it or onto nothing", async () => {
    const { user, trigger } = setup();

    await user.click(trigger);
    await user.tab();
    expect(link("Champions")).toHaveFocus();
    fireEvent.blur(link("Champions"), { relatedTarget: null });
    expect(trigger).toHaveAttribute("aria-expanded", "true");

    link("Rulebook").focus();
    await user.tab();
    expect(screen.getByRole("button", { name: "Elsewhere" })).toHaveFocus();
    expect(trigger).toHaveAttribute("aria-expanded", "false");
  });

  it("closes when a link is chosen", async () => {
    const { user, trigger } = setup();

    await user.click(trigger);
    // Following the link is the router's job, and jsdom cannot navigate: cancel it before it starts.
    document.addEventListener("click", (event) => event.preventDefault(), { capture: true, once: true });
    await user.click(link("Rulebook"));
    expect(trigger).toHaveAttribute("aria-expanded", "false");
  });

  it("opens from the keyboard: ArrowDown lands on the first link, ArrowUp on the last, both wrap", async () => {
    const { user, trigger } = setup();

    trigger.focus();
    await user.keyboard("{ArrowDown}");
    expect(trigger).toHaveAttribute("aria-expanded", "true");
    expect(link("Champions")).toHaveFocus();
    await user.keyboard("{ArrowUp}");
    expect(link("Rulebook")).toHaveFocus();
    await user.keyboard("{ArrowDown}");
    expect(link("Champions")).toHaveFocus();

    await user.keyboard("{Escape}");
    await user.keyboard("{ArrowUp}");
    expect(link("Rulebook")).toHaveFocus();
  });

  it("leaves other keys alone", async () => {
    const { user, trigger } = setup();

    trigger.focus();
    await user.keyboard("m");
    expect(trigger).toHaveAttribute("aria-expanded", "false");
  });

  it("marks its section on one of its screens: the underline on Reference, aria-current on the link", async () => {
    const { user, trigger } = setup("/race-control/champions/1988");

    expect(trigger).toHaveClass("text-rc-ink");
    expect(trigger.querySelector("span.bg-f1-red")).not.toBeNull();
    await user.click(trigger);
    expect(link("Champions")).toHaveAttribute("aria-current", "true");
    expect(link("Rulebook")).not.toHaveAttribute("aria-current");
  });

  it("calls the link to this very page the page", async () => {
    const { user, trigger } = setup("/race-control/rulebook");

    await user.click(trigger);
    expect(link("Rulebook")).toHaveAttribute("aria-current", "page");
  });

  it("has no underline off its screens", () => {
    const { trigger } = setup();
    expect(trigger.querySelector("span.bg-f1-red")).toBeNull();
  });
});
