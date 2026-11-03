import { render, screen } from "@testing-library/react";
import { renderToString } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { PageHero } from "./PageHero";
import { f1, rc } from "./tokens";

/** Mercedes' team colour, as a team page would pass it from the data. */
const MERCEDES = "#27f4d2";

function rule(container: HTMLElement): HTMLElement | null {
  return container.querySelector("[data-hero-rule]");
}

describe("PageHero", () => {
  it("titles a page with an eyebrow, the display title, a red rule and a meta line", () => {
    const { container } = render(
      <PageHero eyebrow="2026 constructors · after round 19" title="Eleven teams" meta="Every team's points." />,
    );

    const title = screen.getByRole("heading", { level: 1, name: "Eleven teams" });
    expect(title).toHaveClass("font-display", "uppercase", "text-[clamp(48px,5.4vw,84px)]");
    expect(screen.getByText("2026 constructors · after round 19")).toHaveClass("font-mono", "text-rc-ink-3");
    expect(screen.getByText("Every team's points.")).toHaveClass("text-rc-ink-2");

    expect(rule(container)).toHaveAttribute("aria-hidden", "true");
    expect(rule(container)).toHaveStyle({ backgroundColor: f1.red });

    const hero = container.firstElementChild;
    expect(hero?.tagName).toBe("HEADER");
    expect(hero).not.toHaveAttribute("data-band");
    expect(hero).not.toHaveClass("lg:grid-cols-[5fr_6fr]");
  });

  it("renders only the title when that is all it is given", () => {
    const { container } = render(<PageHero title="Ask the rulebook" />);

    const hero = container.firstElementChild;
    expect(hero?.querySelectorAll("p")).toHaveLength(0);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Ask the rulebook");
    expect(rule(container)).toBeInTheDocument();
  });

  it("frames an entity page on the band, its edge and rule in the team's colour, the lineup beside it", () => {
    const { container } = render(
      <PageHero
        band
        accent={MERCEDES}
        eyebrow="Constructors' championship · 2026"
        title="Mercedes"
        aside={<p>Lineup</p>}
      >
        <p>P1 · 630 points</p>
      </PageHero>,
    );

    const hero = container.firstElementChild;
    expect(hero).toHaveAttribute("data-band");
    expect(hero).toHaveClass("bg-rc-hero", "border-rc-line", "lg:grid-cols-[1.1fr_1fr]");
    expect(screen.getByRole("heading", { level: 1 })).toHaveClass("text-[clamp(64px,8vw,120px)]");

    const edge = hero?.firstElementChild;
    expect(edge).toHaveAttribute("aria-hidden", "true");
    expect(edge).toHaveStyle({ backgroundColor: MERCEDES });
    expect(rule(container)).toHaveStyle({ backgroundColor: MERCEDES });

    expect(screen.getByText("Lineup").parentElement).toHaveClass("lg:border-l");
    expect(screen.getByText("P1 · 630 points").parentElement).toHaveClass("mt-8");
  });

  it("sets the aside beside the title on a plain hero too, such as the circuit map", () => {
    const { container } = render(<PageHero title="São Paulo Grand Prix" aside={<figure>Map</figure>} />);

    expect(container.firstElementChild).toHaveClass("lg:grid-cols-[5fr_6fr]");
    expect(screen.getByText("Map").parentElement).not.toHaveClass("lg:border-l");
  });

  it.each([
    ["missing", null],
    ["blank", "  "],
  ])("falls back to the brand red for a %s team colour", (_case, accent) => {
    const { container } = render(<PageHero band accent={accent} title="Cadillac" />);

    expect(container.firstElementChild?.firstElementChild).toHaveStyle({ backgroundColor: f1.red });
    expect(rule(container)).toHaveStyle({ backgroundColor: f1.red });
  });

  it("takes gold for a champion", () => {
    const { container } = render(<PageHero accent={rc.gold} title="Kimi Antonelli" />);
    expect(rule(container)).toHaveStyle({ backgroundColor: rc.gold });
  });

  it("enters only behind motion-safe, so the server's HTML is the hero at rest", () => {
    const html = renderToString(<PageHero eyebrow="Round 20" title="São Paulo" meta="Interlagos" />);

    expect(html).toContain("motion-safe:animate-fade-up");
    expect(html).toContain("motion-safe:animate-fill-x");
    expect(html).not.toMatch(/(^|[\s"])animate-/);
  });
});
