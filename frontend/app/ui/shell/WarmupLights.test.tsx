import { act, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { LAUNCH_DURATION_MS, type ServerState } from "@/app/lib/serverStatus";

import { LIGHTS_OUT_AFTER_MS, WarmupLights } from "./WarmupLights";

const server = (patch: Partial<ServerState> = {}): ServerState => ({
  status: "warming",
  detail: "Loading the race prediction model",
  stage: "model",
  lit: 3,
  run: 1,
  waited: true,
  warmingSince: Date.now(),
  dismissedRun: 0,
  launchedRun: 0,
  ...patch,
});

const lamps = (container: HTMLElement) => Array.from(container.querySelectorAll("i"));
const lit = (container: HTMLElement) => lamps(container).filter((lamp) => lamp.classList.contains("bg-f1-red"));

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

describe("WarmupLights", () => {
  it("lights as many lamps as the stage reached, with the count and the stage detail", () => {
    const { container } = render(<WarmupLights phase="warming" server={server()} />);

    expect(lamps(container)).toHaveLength(5);
    expect(lit(container)).toHaveLength(3);
    expect(screen.getByText("Server starting")).toBeInTheDocument();
    expect(screen.getByText("3/5")).toBeInTheDocument();
    expect(screen.getByRole("tooltip")).toHaveTextContent("Loading the race prediction model");
    expect(screen.getByRole("tooltip")).toHaveTextContent("Stage 3 of 5 · 0:00");
    expect(screen.getByRole("tooltip")).toHaveTextContent("waking from sleep on the free tier");
  });

  it("leaves lit lamps free of any loop and unlit ones undecorated", () => {
    const { container } = render(<WarmupLights phase="warming" server={server({ lit: 1 })} />);

    expect(container.innerHTML).not.toContain("glow");
    expect(container.innerHTML).not.toContain("infinite");
    expect(lamps(container)[1]).not.toHaveClass("motion-safe:animate-lights-out");
    expect(lit(container)[0]).toHaveClass("motion-safe:animate-light-on");
  });

  it("counts the seconds the run has waited", () => {
    render(<WarmupLights phase="warming" server={server({ warmingSince: Date.now() })} />);

    act(() => void vi.advanceTimersByTime(65_000));
    expect(screen.getByRole("tooltip")).toHaveTextContent("Stage 3 of 5 · 1:05");
  });

  it("falls back to the plain detail before the backend has answered", () => {
    render(<WarmupLights phase="warming" server={server({ detail: null, warmingSince: null, lit: 1 })} />);

    expect(screen.getByRole("tooltip")).toHaveTextContent("Server starting up");
    expect(screen.getByRole("tooltip")).toHaveTextContent("Stage 1 of 5 · 0:00");
  });

  it("says back online with five lit, then all five go dark together", () => {
    const { container } = render(<WarmupLights phase="launching" server={server({ status: "ready", lit: 5 })} />);

    expect(screen.getByText("Back online")).toBeInTheDocument();
    expect(lit(container)).toHaveLength(5);
    act(() => void vi.advanceTimersByTime(LIGHTS_OUT_AFTER_MS));
    expect(lit(container)).toHaveLength(0);
    expect(lamps(container)[0]).toHaveClass("motion-safe:animate-lights-out");
    expect(LIGHTS_OUT_AFTER_MS).toBeLessThan(LAUNCH_DURATION_MS);
  });

  it("holds the highest count in red words when the server isn't responding", () => {
    const { container } = render(
      <WarmupLights phase="unreachable" server={server({ status: "unreachable", lit: 2 })} />,
    );

    expect(lit(container)).toHaveLength(2);
    expect(screen.getByText("Not responding").parentElement).toHaveClass("text-rc-red-text");
    expect(screen.getByText("No response")).toBeInTheDocument();
    expect(screen.queryByRole("tooltip")).toBeNull();
  });
});
