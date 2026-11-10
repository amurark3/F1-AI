import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { SAO_PAULO_2026, SESSION_WEATHER_2026 } from "@/test/fixtures";

import { SessionWeatherStrip } from "./SessionWeatherStrip";

function cells(): HTMLElement[] {
  return within(screen.getByRole("list", { name: "Weather by session" })).getAllByRole("listitem");
}

describe("SessionWeatherStrip", () => {
  it("shows each São Paulo session's glyph, temperature and rain chance", () => {
    render(<SessionWeatherStrip rows={SAO_PAULO_2026.weather.sessions} />);

    expect(cells().map((cell) => cell.textContent)).toEqual([
      "FP125°12%",
      "FP223°15%",
      "FP327°43%",
      "Quali24°80%",
      "Race17°21%",
    ]);
    expect(screen.getByRole("img", { name: "Thunderstorm" })).toBeInTheDocument();
    expect(screen.getByText("80%")).toHaveStyle({ color: "#4C8DFF" });
    expect(cells().at(-1)).toHaveClass("border-[#E10600]/50");
    expect(cells()[0]).toHaveClass("border-white/10");
    expect(screen.queryByText(/as of/)).not.toBeInTheDocument();
  });

  it("says when a stored forecast was fetched, under the sessions it fills", () => {
    render(<SessionWeatherStrip rows={SAO_PAULO_2026.weather.sessions} asOf="as of 6 Nov 14:05 UTC" />);

    expect(cells()).toHaveLength(5);
    expect(screen.getByText("Forecast as of 6 Nov 14:05 UTC")).toHaveClass("text-rc-ink-3");
  });

  it("abbreviates sprint sessions", () => {
    render(<SessionWeatherStrip rows={SESSION_WEATHER_2026.singaporeDone.sessions} />);
    expect(cells().map((cell) => cell.firstElementChild?.textContent)).toEqual([
      "FP1",
      "SQ",
      "Sprint",
      "Quali",
      "Race",
    ]);
  });

  it("leaves an empty ring and a dash before a session's forecast opens", () => {
    render(<SessionWeatherStrip rows={SESSION_WEATHER_2026.lasVegasPending.sessions} />);
    const [practice] = cells();
    expect(practice).toHaveTextContent(/^FP1—$/);
    expect(practice.querySelector('[aria-hidden="true"].border-dashed')).toBeInTheDocument();
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
  });

  it("shows a dash for blank readings rather than a dry zero", () => {
    const [practice] = SAO_PAULO_2026.weather.sessions;
    render(<SessionWeatherStrip rows={[{ ...practice, forecast: SESSION_WEATHER_2026.blankHour }]} />);
    expect(cells()[0]).toHaveTextContent(/^FP1—$/);
    expect(screen.getByRole("img", { name: "Unclassified" })).toBeInTheDocument();
    expect(screen.queryByText(/%/)).not.toBeInTheDocument();
  });

  it("shows a session the timing screens have no short name for as sent", () => {
    // FastF1 names pre-season testing days "Day 1" to "Day 3"; the schedule leaves testing out today.
    const [practice] = SAO_PAULO_2026.weather.sessions;
    render(<SessionWeatherStrip rows={[{ ...practice, name: "Day 1" }]} />);
    expect(cells()[0].firstElementChild).toHaveTextContent("Day 1");
  });

  it("renders nothing until the weather segment lands", () => {
    const { container } = render(<SessionWeatherStrip rows={[]} />);
    expect(container).toBeEmptyDOMElement();
  });
});
