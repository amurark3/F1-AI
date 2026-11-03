import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";

import { Segmented, type SegmentedOption, type SegmentedProps } from "./Segmented";

type Table = "drivers" | "teams" | "rookies";

const TABLES: ReadonlyArray<SegmentedOption<Table>> = [
  { value: "drivers", label: "Drivers" },
  { value: "teams", label: "Teams" },
  { value: "rookies", label: "Rookies" },
];

/** A controlled Segmented, as a page would hold it, reporting each change. */
function Harness({ initial = "drivers", onChange, ...props }: Partial<SegmentedProps<Table>> & { initial?: Table }) {
  const [value, setValue] = useState<Table>(initial);
  return (
    <Segmented
      label="Championship"
      options={TABLES}
      {...props}
      value={value}
      onChange={(next) => {
        setValue(next);
        onChange?.(next);
      }}
    />
  );
}

describe("Segmented", () => {
  it("is a named radio group with one option checked, raised, and the only tab stop", () => {
    render(<Harness className="ml-auto" />);

    const group = screen.getByRole("radiogroup", { name: "Championship" });
    expect(group).toHaveClass("ml-auto", "border-rc-line", "bg-background");

    const drivers = screen.getByRole("radio", { name: "Drivers" });
    expect(drivers).toBeChecked();
    expect(drivers).toHaveAttribute("tabindex", "0");
    expect(drivers).toHaveClass("bg-rc-raised", "text-rc-ink", "focus-visible:outline-rc-red-text");

    const teams = screen.getByRole("radio", { name: "Teams" });
    expect(teams).not.toBeChecked();
    expect(teams).toHaveAttribute("tabindex", "-1");
    expect(teams).toHaveClass("text-rc-ink-3");
  });

  it("chooses on click, and ignores a click on the option already chosen", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn<(value: Table) => void>();
    render(<Harness onChange={onChange} />);

    await user.click(screen.getByRole("radio", { name: "Drivers" }));
    expect(onChange).not.toHaveBeenCalled();

    await user.click(screen.getByRole("radio", { name: "Teams" }));
    expect(onChange).toHaveBeenCalledExactlyOnceWith("teams");
    expect(screen.getByRole("radio", { name: "Teams" })).toBeChecked();
  });

  it("moves and chooses with every arrow key, wrapping at either end", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn<(value: Table) => void>();
    render(<Harness onChange={onChange} />);

    await user.tab();
    expect(screen.getByRole("radio", { name: "Drivers" })).toHaveFocus();

    await user.keyboard("{ArrowRight}");
    expect(screen.getByRole("radio", { name: "Teams" })).toHaveFocus();
    expect(screen.getByRole("radio", { name: "Teams" })).toBeChecked();

    await user.keyboard("{ArrowDown}{ArrowDown}");
    expect(screen.getByRole("radio", { name: "Drivers" })).toHaveFocus();

    await user.keyboard("{ArrowLeft}");
    expect(screen.getByRole("radio", { name: "Rookies" })).toHaveFocus();

    await user.keyboard("{ArrowUp}{Home}");
    expect(screen.getByRole("radio", { name: "Drivers" })).toHaveFocus();

    await user.keyboard("{End}");
    expect(screen.getByRole("radio", { name: "Rookies" })).toBeChecked();
    expect(onChange.mock.calls.map(([value]) => value)).toEqual([
      "teams",
      "rookies",
      "drivers",
      "rookies",
      "teams",
      "drivers",
      "rookies",
    ]);
  });

  it("leaves other keys to the page", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn<(value: Table) => void>();
    render(<Harness onChange={onChange} />);

    await user.tab();
    await user.keyboard("a{Enter}");
    expect(onChange).not.toHaveBeenCalled();
  });

  it("skips a disabled option and keeps the group reachable when the choice is not available", async () => {
    const user = userEvent.setup();
    const options = TABLES.map((option) => ({ ...option, disabled: option.value === "teams" }));
    render(<Harness options={options} initial="teams" />);

    const teams = screen.getByRole("radio", { name: "Teams" });
    expect(teams).toBeDisabled();
    expect(teams).toHaveClass("disabled:opacity-40");
    expect(screen.getByRole("radio", { name: "Drivers" })).toHaveAttribute("tabindex", "0");

    await user.tab();
    await user.keyboard("{ArrowRight}");
    expect(screen.getByRole("radio", { name: "Rookies" })).toHaveFocus();
    expect(screen.getByRole("radio", { name: "Rookies" })).toBeChecked();
  });

  it("offers no tab stop when every option is disabled", () => {
    render(<Harness options={TABLES.map((option) => ({ ...option, disabled: true }))} />);

    for (const radio of screen.getAllByRole("radio")) expect(radio).toHaveAttribute("tabindex", "-1");
  });

  it("acts as tabs for a panel per option, on the horizontal arrows only", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn<(value: Table) => void>();
    render(<Harness semantics="tablist" controls="phase-panel" label="Prediction phase" onChange={onChange} />);

    expect(screen.getByRole("tablist", { name: "Prediction phase" })).toBeInTheDocument();
    const drivers = screen.getByRole("tab", { name: "Drivers" });
    expect(drivers).toHaveAttribute("aria-selected", "true");
    expect(drivers).toHaveAttribute("aria-controls", "phase-panel");
    expect(drivers).not.toHaveAttribute("aria-checked");

    await user.tab();
    await user.keyboard("{ArrowDown}");
    expect(onChange).not.toHaveBeenCalled();

    await user.keyboard("{ArrowRight}");
    expect(screen.getByRole("tab", { name: "Teams" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tab", { name: "Teams" })).toHaveFocus();
  });
});
