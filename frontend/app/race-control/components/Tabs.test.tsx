import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";

import { TabPanel, Tabs, panelId, tabId, type TabItem } from "./Tabs";

type Key = "weekend" | "sessions" | "grid" | "stints";

const ITEMS: ReadonlyArray<TabItem<Key>> = [
  { key: "weekend", label: "Weekend", title: "Schedule and circuit" },
  { key: "sessions", label: "Sessions" },
  { key: "grid", label: "Grid", disabled: true },
  { key: "stints", label: "Stints" },
];

function Harness({ variant, start = "weekend" }: { variant?: "underline" | "segmented"; start?: Key }) {
  const [active, setActive] = useState<Key>(start);
  return (
    <>
      <Tabs items={ITEMS} active={active} onChange={setActive} idPrefix="gp" label="Grand Prix" variant={variant} />
      <TabPanel idPrefix="gp" active={active} className="pt-4">
        Panel for {active}
      </TabPanel>
    </>
  );
}

describe("tab ids", () => {
  it("tie each tab to the one panel", () => {
    expect(tabId("gp", "grid")).toBe("gp-tab-grid");
    expect(panelId("gp")).toBe("gp-panel");
  });
});

describe("Tabs", () => {
  it("follows the tabs pattern: one tab stop, selection and the panel it controls", () => {
    render(<Harness />);

    expect(screen.getByRole("tablist", { name: "Grand Prix" })).toBeInTheDocument();
    const weekend = screen.getByRole("tab", { name: "Weekend" });
    expect(weekend).toHaveAttribute("aria-selected", "true");
    expect(weekend).toHaveAttribute("tabindex", "0");
    expect(weekend).toHaveAttribute("aria-controls", "gp-panel");
    expect(weekend).toHaveAttribute("title", "Schedule and circuit");
    expect(screen.getByRole("tab", { name: "Sessions" })).toHaveAttribute("tabindex", "-1");
    expect(screen.getByRole("tab", { name: "Grid" })).toBeDisabled();

    const panel = screen.getByRole("tabpanel");
    expect(panel).toHaveAttribute("id", "gp-panel");
    expect(panel).toHaveAttribute("aria-labelledby", "gp-tab-weekend");
    expect(panel).toHaveClass("pt-4");
    expect(weekend.querySelector("[aria-hidden]")).toHaveClass("bg-[#E10600]");
  });

  it("chooses a tab on click", async () => {
    const user = userEvent.setup();
    render(<Harness />);

    await user.click(screen.getByRole("tab", { name: "Sessions" }));

    expect(screen.getByRole("tab", { name: "Sessions" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tabpanel")).toHaveTextContent("Panel for sessions");
  });

  it("moves with the arrows, wraps, skips a disabled tab and jumps with Home and End", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    const tab = (name: string) => screen.getByRole("tab", { name });

    await user.click(tab("Weekend"));
    await user.keyboard("{ArrowRight}");
    expect(tab("Sessions")).toHaveFocus();
    await user.keyboard("{ArrowRight}");
    expect(tab("Stints")).toHaveFocus();
    expect(tab("Stints")).toHaveAttribute("aria-selected", "true");
    await user.keyboard("{ArrowRight}");
    expect(tab("Weekend")).toHaveFocus();
    await user.keyboard("{ArrowLeft}");
    expect(tab("Stints")).toHaveFocus();
    await user.keyboard("{Home}");
    expect(tab("Weekend")).toHaveFocus();
    await user.keyboard("{End}");
    expect(tab("Stints")).toHaveFocus();
  });

  it("ignores keys that do not move", async () => {
    const user = userEvent.setup();
    render(<Harness start="sessions" />);

    await user.click(screen.getByRole("tab", { name: "Sessions" }));
    await user.keyboard("{ArrowDown}a");

    expect(screen.getByRole("tab", { name: "Sessions" })).toHaveAttribute("aria-selected", "true");
  });

  it("does nothing on arrows when every tab is disabled", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn<(key: Key) => void>();
    render(
      <Tabs
        items={ITEMS.map((item) => ({ ...item, disabled: true }))}
        active="weekend"
        onChange={onChange}
        idPrefix="all-off"
        label="Off"
      />,
    );

    screen.getByRole("tab", { name: "Weekend" }).focus();
    await user.keyboard("{ArrowRight}");

    expect(onChange).not.toHaveBeenCalled();
  });

  it("starts from the first enabled tab when the active one is not enabled", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn<(key: Key) => void>();
    render(<Tabs items={ITEMS} active="grid" onChange={onChange} idPrefix="gp" label="Grand Prix" />);

    screen.getByRole("tab", { name: "Weekend" }).focus();
    await user.keyboard("{ArrowRight}");

    expect(onChange).toHaveBeenLastCalledWith("sessions");
  });

  it("draws the segmented look without the underline", () => {
    render(<Harness variant="segmented" />);

    expect(screen.getByRole("tablist")).toHaveClass("rounded-md", "p-1");
    const weekend = screen.getByRole("tab", { name: "Weekend" });
    expect(weekend).toHaveClass("bg-[#E10600]/15");
    expect(weekend.querySelector("[aria-hidden]")).toBeNull();
  });

  it("draws the shared focus ring inside each tab, clear of the scrolling list's edge", () => {
    render(<Harness />);

    for (const tab of screen.getAllByRole("tab")) {
      expect(tab).toHaveClass("focus-visible:-outline-offset-2");
      expect(tab.className).not.toMatch(/ring/);
    }
  });
});
