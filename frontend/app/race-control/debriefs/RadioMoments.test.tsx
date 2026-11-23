import { act, fireEvent, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi, type MockInstance } from "vitest";

import { useServerStatus, type ServerState } from "@/app/hooks/useServerStatus";
import { DIRECTORY_2026 } from "@/test/fixtures";
import { DEBRIEF_RADIO_R19 } from "@/test/fixtures/debrief";
import { apiUrl, server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";

import { RadioMoments } from "./RadioMoments";

import type { DebriefRadio, RadioClip, RadioMoment } from "./debriefTypes";

vi.mock("@/app/hooks/useServerStatus", () => ({ useServerStatus: vi.fn() }));

const LEC_PLAY = "Play Charles Leclerc team radio, lap 43, 15:02:27";
const NOR_PLAY = "Play Lando Norris team radio, before the start, 13:59:28";
const LEC_URL = DEBRIEF_RADIO_R19.moments[2].clips[0].url;

let play: MockInstance<HTMLMediaElement["play"]>;
let pause: MockInstance<HTMLMediaElement["pause"]>;

const made = new Set<HTMLMediaElement>();

function audio(): HTMLAudioElement {
  return [...made][0];
}

function setMedia(values: { duration?: number; currentTime?: number }) {
  for (const [key, value] of Object.entries(values)) {
    Object.defineProperty(audio(), key, { configurable: true, value });
  }
}

function render(radio: DebriefRadio = DEBRIEF_RADIO_R19) {
  return renderWithProviders(<RadioMoments radio={radio} />);
}

const CLIP: RadioClip = { ...DEBRIEF_RADIO_R19.moments[0].clips[1], lap: 5 };

function moment(changes: Partial<RadioMoment>): RadioMoment {
  return {
    kind: "stop",
    lap: 5,
    at: CLIP.at,
    driver: { driver_code: "NOR", driver_name: "Lando Norris", team: "McLaren" },
    detail: "2.4 s",
    clips: [CLIP],
    ...changes,
  };
}

function hand(moments: RadioMoment[], changes: Partial<DebriefRadio> = {}): DebriefRadio {
  return { ...DEBRIEF_RADIO_R19, moments, unattached: [], ...changes };
}

describe("RadioMoments", () => {
  beforeEach(() => {
    made.clear();
    vi.mocked(useServerStatus).mockReturnValue({ status: "ready" } as ServerState);
    server.use(http.get(apiUrl("/api/profiles/:year/directory"), () => HttpResponse.json(DIRECTORY_2026)));
    // jsdom plays nothing, so the stubs keep `paused` honest the way a browser does.
    play = vi.spyOn(HTMLMediaElement.prototype, "play").mockImplementation(function (this: HTMLMediaElement) {
      made.add(this);
      Object.defineProperty(this, "paused", { configurable: true, value: false });
      return Promise.resolve();
    });
    pause = vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(function (this: HTMLMediaElement) {
      Object.defineProperty(this, "paused", { configurable: true, value: true });
      this.dispatchEvent(new Event("pause"));
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("lists the moments with their clips, the closed unattached group and the note", () => {
    render();

    expect(screen.getByText("Team radio · audio, no transcript")).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "14 of 27 clips came within a lap of a race moment" }),
    ).toBeInTheDocument();
    const text = document.body.textContent ?? "";
    for (const part of [
      "Formation lap and start",
      "Turn 4 · with LEC",
      "Red flag · race suspended",
      "Turn 2 · with LIN",
      "Safety Car in",
      "Chequered flag",
    ]) {
      expect(text).toContain(part);
    }
    expect(
      ["Start", "Incident", "Safety Car", "Red flag", "Flag"].every((tag) => screen.getAllByText(tag).length > 0),
    ).toBe(true);
    expect(["2 clips", "1 clip", "4 clips"].every((count) => screen.getAllByText(count).length > 0)).toBe(true);
    for (const lap of ["L1", "L44", "L45", "L59", "L62", "L71"])
      expect(screen.getAllByText(lap).length).toBeGreaterThan(0);
    const summary = screen.getByText("13 more clips, not within a lap of a race moment");
    expect(summary.closest("details")).not.toHaveAttribute("open");
    expect(screen.getByRole("button", { name: NOR_PLAY })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: LEC_PLAY })).toBeInTheDocument();
    expect(document.body.textContent).toMatch(/times are local \(UTC−6\)$/);
    expect(document.querySelector("audio")).toBeNull();
    expect(within(summary.closest("details") as HTMLElement).getAllByRole("button", { hidden: true })).toHaveLength(13);
  });

  it("plays one clip, shows progress from the audio's metadata, pauses, switches and ends", async () => {
    const user = userEvent.setup();
    render();

    await user.click(screen.getByRole("button", { name: LEC_PLAY }));
    expect(play).toHaveBeenCalledTimes(1);
    expect(audio().src).toBe(LEC_URL);
    const playing = screen.getByRole("button", { name: "Pause Charles Leclerc team radio" });
    expect(playing).toHaveAttribute("aria-pressed", "true");
    expect(playing).toHaveTextContent("0:00");
    expect(playing).not.toHaveTextContent("/");

    setMedia({ duration: 10, currentTime: 4 });
    act(() => {
      fireEvent.loadedMetadata(audio());
      fireEvent.timeUpdate(audio());
    });
    expect(playing).toHaveTextContent("0:04 / 0:10");
    expect(playing.querySelector("span span:last-child span, span span")).toHaveStyle({ width: "40%" });
    setMedia({ duration: Number.POSITIVE_INFINITY });
    act(() => {
      fireEvent.durationChange(audio());
    });
    expect(playing).toHaveTextContent("0:04");
    expect(playing).not.toHaveTextContent("/");

    await user.click(playing);
    expect(pause).toHaveBeenCalledTimes(1);
    const paused = screen.getByRole("button", { name: LEC_PLAY });
    expect(paused).toHaveAttribute("aria-pressed", "false");
    expect(paused).toHaveTextContent("0:04");

    await user.click(paused);
    expect(play).toHaveBeenCalledTimes(2);
    act(() => {
      fireEvent.play(audio());
    });
    expect(screen.getByRole("button", { name: "Pause Charles Leclerc team radio" })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: NOR_PLAY }));
    expect(audio().src).not.toBe(LEC_URL);
    expect(screen.getByRole("button", { name: LEC_PLAY })).toHaveTextContent("15:02:27");

    act(() => {
      fireEvent.ended(audio());
    });
    expect(screen.queryByRole("button", { name: /^Pause/ })).not.toBeInTheDocument();
  });

  it("marks a clip that fails to load, and resets one the browser blocks", async () => {
    const user = userEvent.setup();
    render();

    await user.click(screen.getByRole("button", { name: LEC_PLAY }));
    act(() => {
      fireEvent.error(audio());
    });
    const failed = screen.getByRole("button", { name: `${LEC_PLAY} (couldn't load)` });
    expect(failed).toHaveTextContent("Can't play");

    play.mockRejectedValueOnce(new DOMException("blocked", "NotAllowedError"));
    await user.click(screen.getByRole("button", { name: NOR_PLAY }));
    expect(await screen.findByRole("button", { name: NOR_PLAY })).toHaveAttribute("aria-pressed", "false");
  });

  it("keeps the clip it switched to when the old clip's play() is aborted", async () => {
    const user = userEvent.setup();
    render();
    let abort: (reason: DOMException) => void = () => undefined;
    play.mockReturnValueOnce(
      new Promise<void>((_resolve, reject) => {
        abort = reject;
      }),
    );

    await user.click(screen.getByRole("button", { name: LEC_PLAY }));
    await user.click(screen.getByRole("button", { name: NOR_PLAY }));
    await act(async () => {
      abort(new DOMException("switched", "AbortError"));
      await Promise.resolve();
    });

    expect(await screen.findByRole("button", { name: "Pause Lando Norris team radio" })).toBeInTheDocument();
  });

  it("titles stop, penalty and retirement moments with the driver and tags them", () => {
    render(
      hand([
        moment({}),
        moment({ kind: "penalty", detail: "5 second time penalty" }),
        moment({ kind: "retirement", detail: null }),
        moment({ kind: "vsc", driver: null, detail: null }),
      ]),
    );

    expect(document.body.textContent).toContain("Lando Norris stops · 2.4 s");
    expect(document.body.textContent).toContain("Lando Norris · 5 second time penalty");
    expect(document.body.textContent).toContain("Lando Norris retires");
    expect(document.body.textContent).toContain("Virtual Safety Car deployed");
    for (const tag of ["Stop", "Penalty", "DNF", "VSC"]) expect(screen.getByText(tag)).toBeInTheDocument();
    expect(document.querySelector("details")).toBeNull();
  });

  it("reads times in UTC when the circuit's offset is unknown", () => {
    render(hand([moment({ kind: "start", driver: null, detail: null })], { utc_offset_minutes: null }));

    expect(screen.getByRole("button", { name: /^Play Lando Norris team radio, lap 5, 19:59:28$/ })).toBeInTheDocument();
    expect(document.body.textContent).toMatch(/times in UTC$/);
  });

  it("says why there is no radio, with no list and no note", () => {
    render({ ...hand([]), available: false, reason: "OpenF1 has no team radio for this race.", total: 0 });

    expect(screen.getByText("Team radio · audio, no transcript")).toBeInTheDocument();
    expect(screen.getByText("OpenF1 has no team radio for this race.")).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    expect(document.querySelector("audio")).toBeNull();
  });
});
