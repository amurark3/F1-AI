import { fireEvent, render, screen } from "@testing-library/react";
import { useRef } from "react";
import { describe, expect, it, vi } from "vitest";

import { useDismiss, type DismissReason } from "./useDismiss";

function Harness({ open, onDismiss }: { open: boolean; onDismiss: (reason: DismissReason) => void }) {
  const ref = useRef<HTMLDivElement>(null);
  useDismiss(open, ref, onDismiss);
  return (
    <>
      <div ref={ref}>
        <button type="button">Inside</button>
      </div>
      <button type="button">Outside</button>
    </>
  );
}

describe("useDismiss", () => {
  it("reports Escape pressed anywhere", () => {
    const onDismiss = vi.fn();
    render(<Harness open onDismiss={onDismiss} />);

    fireEvent.keyDown(document.body, { key: "Escape" });
    expect(onDismiss).toHaveBeenCalledWith("escape");
  });

  it("ignores other keys", () => {
    const onDismiss = vi.fn();
    render(<Harness open onDismiss={onDismiss} />);

    fireEvent.keyDown(document.body, { key: "Enter" });
    expect(onDismiss).not.toHaveBeenCalled();
  });

  it("reports a press outside the container, never one inside it", () => {
    const onDismiss = vi.fn();
    render(<Harness open onDismiss={onDismiss} />);

    fireEvent.pointerDown(screen.getByRole("button", { name: "Inside" }));
    expect(onDismiss).not.toHaveBeenCalled();
    fireEvent.pointerDown(screen.getByRole("button", { name: "Outside" }));
    expect(onDismiss).toHaveBeenCalledWith("outside");
  });

  it("counts every press as outside when the container is not mounted", () => {
    const onDismiss = vi.fn();
    function Unmounted() {
      const ref = useRef<HTMLDivElement>(null);
      useDismiss(true, ref, onDismiss);
      return <button type="button">Anywhere</button>;
    }
    render(<Unmounted />);

    fireEvent.pointerDown(screen.getByRole("button", { name: "Anywhere" }));
    expect(onDismiss).toHaveBeenCalledWith("outside");
  });

  it("listens only while open, and stops when it closes", () => {
    const onDismiss = vi.fn();
    const { rerender } = render(<Harness open={false} onDismiss={onDismiss} />);
    fireEvent.keyDown(document.body, { key: "Escape" });
    expect(onDismiss).not.toHaveBeenCalled();

    rerender(<Harness open onDismiss={onDismiss} />);
    rerender(<Harness open={false} onDismiss={onDismiss} />);
    fireEvent.keyDown(document.body, { key: "Escape" });
    fireEvent.pointerDown(document.body);
    expect(onDismiss).not.toHaveBeenCalled();
  });
});
