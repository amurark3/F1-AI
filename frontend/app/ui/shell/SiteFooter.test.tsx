import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { MORE_NAV, PRIMARY_NAV } from "./navConfig";
import { F1DisclaimerLine, SiteFooter } from "./SiteFooter";

/** The standard trade-mark notice, word for word: it must never be reworded. */
const DISCLAIMER =
  "This site is unofficial and is not associated in any way with the Formula 1 companies. " +
  "F1, FORMULA ONE, FORMULA 1, FIA FORMULA ONE WORLD CHAMPIONSHIP, GRAND PRIX and related " +
  "marks are trade marks of Formula One Licensing B.V.";

const footer = () => screen.getByRole("contentinfo");

describe("SiteFooter", () => {
  it("links every screen the top bar and More menu hold, in their order", () => {
    render(<SiteFooter />);

    const links = within(within(footer()).getByRole("navigation", { name: "Footer" })).getAllByRole("link");
    expect(links.map((link) => [link.textContent, link.getAttribute("href")])).toEqual(
      [...PRIMARY_NAV, ...MORE_NAV].map(({ label, href }) => [label, href]),
    );
  });

  it("prints the F1 trade-mark disclaimer verbatim", () => {
    render(<SiteFooter />);

    expect(within(footer()).getByText(DISCLAIMER)).toBeInTheDocument();
  });

  it("credits each data source with a link that opens in a new tab", () => {
    render(<SiteFooter />);

    const credits = within(footer()).getByText(/^Data:/);
    const sources = within(credits).getAllByRole("link");
    expect(sources.map((link) => [link.textContent, link.getAttribute("href")])).toEqual([
      ["f1db", "https://github.com/f1db/f1db"],
      ["OpenF1", "https://openf1.org"],
      ["FastF1", "https://github.com/theOehrly/Fast-F1"],
      ["Open-Meteo", "https://open-meteo.com"],
      ["OpenWeatherMap", "https://openweathermap.org"],
    ]);
    for (const link of sources) {
      expect(link).toHaveAttribute("target", "_blank");
      expect(link).toHaveAttribute("rel", "noopener noreferrer");
    }
    expect(credits).toHaveTextContent("Data: f1db · OpenF1 · FastF1 · Open-Meteo · OpenWeatherMap");
  });
});

describe("F1DisclaimerLine", () => {
  it("prints the same disclaimer as fine print in the label tone", () => {
    render(<F1DisclaimerLine />);

    expect(screen.getByText(DISCLAIMER)).toHaveClass("text-[10px]", "text-rc-ink-3");
  });

  it("takes the caller's spacing", () => {
    render(<F1DisclaimerLine className="mx-auto text-center" />);

    expect(screen.getByText(DISCLAIMER)).toHaveClass("mx-auto", "text-center", "text-rc-ink-3");
  });
});
