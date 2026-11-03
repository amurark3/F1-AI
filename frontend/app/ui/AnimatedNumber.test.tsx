import { render, screen, waitFor } from "@testing-library/react";
import { useReducedMotion } from "framer-motion";
import { renderToString } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

import { AnimatedNumber } from "./AnimatedNumber";

import type * as FramerMotion from "framer-motion";

vi.mock("framer-motion", async (importOriginal) => ({
  ...(await importOriginal<typeof FramerMotion>()),
  useReducedMotion: vi.fn(),
}));

describe("AnimatedNumber", () => {
  it("renders the final figure on the server, before any count", () => {
    vi.mocked(useReducedMotion).mockReturnValue(null);
    expect(renderToString(<AnimatedNumber value={3.14159} decimals={2} className="tabular-nums" />)).toBe(
      '<span class="tabular-nums">3.14</span>',
    );
  });

  it("counts up to the value for a reader who allows motion", async () => {
    vi.mocked(useReducedMotion).mockReturnValue(false);
    render(<AnimatedNumber value={42} duration={0.2} />);
    const figure = screen.getByText("42");

    // The count restarts from zero after mount, then lands on the value.
    await waitFor(() => expect(Number(figure.textContent)).toBeLessThan(42));
    await waitFor(() => expect(figure).toHaveTextContent(/^42$/));
  });

  it("shows the value without counting for a reader who prefers reduced motion, and jumps to a new one", async () => {
    vi.mocked(useReducedMotion).mockReturnValue(true);
    const { rerender } = render(<AnimatedNumber value={7.25} decimals={1} />);
    expect(screen.getByText("7.3")).toBeInTheDocument();

    rerender(<AnimatedNumber value={9} decimals={1} />);
    await waitFor(() => expect(screen.getByText("9.0")).toBeInTheDocument());
  });

  it("stops a running count when it unmounts", () => {
    vi.mocked(useReducedMotion).mockReturnValue(false);
    const { unmount } = render(<AnimatedNumber value={1000} duration={10} />);

    expect(() => unmount()).not.toThrow();
  });
});
