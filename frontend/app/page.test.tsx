import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import HomePage from "./page";
import { MORE_NAV, PRIMARY_NAV } from "./ui/shell/navConfig";

/** Every screen the site's navigation names: the homepage's links must land on these. */
const NAV_HREFS = [...PRIMARY_NAV, ...MORE_NAV].map((link) => link.href);

/** The text a reader gets: the page without the parts hidden from assistive tech (index numerals, motifs). */
function readableText(container: HTMLElement): string {
  const copy = container.cloneNode(true) as HTMLElement;
  copy.querySelectorAll('[aria-hidden="true"]').forEach((node) => node.remove());
  return copy.textContent;
}

describe("HomePage", () => {
  it("names the product in the hero, with a way into Race Control and one to the AI Engineer", () => {
    render(<HomePage />);

    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(/^Your AI\s*Race Engineer$/);
    expect(screen.getByRole("link", { name: /^Enter Race Control/ })).toHaveAttribute("href", "/race-control");
    expect(screen.getByRole("link", { name: /^Ask the AI Engineer/ })).toHaveAttribute(
      "href",
      "/race-control/engineer",
    );
  });

  it("orders the screens into the three sections of the mockup", () => {
    render(<HomePage />);

    expect(screen.getAllByRole("heading", { level: 2 }).map((heading) => heading.textContent)).toEqual([
      "Race weekend",
      "Decision tools",
      "Reference",
    ]);
    const reference = screen.getByRole("region", { name: "Reference" });
    expect(
      within(reference)
        .getAllByRole("heading", { level: 3 })
        .map((heading) => heading.textContent),
    ).toEqual(["Champions", "Race Debriefs", "Rulebook"]);
  });

  it("links only to screens in the site's navigation, and to every one of them", () => {
    render(<HomePage />);

    const hrefs = screen.getAllByRole("link").map((link) => link.getAttribute("href"));
    expect(hrefs.filter((href) => href == null || !NAV_HREFS.includes(href))).toEqual([]);
    expect(new Set(hrefs)).toEqual(new Set(NAV_HREFS));
  });

  it("offers the AI Engineer's kinds of question without a sample answer", () => {
    render(<HomePage />);

    const questions = screen.getByRole("list", { name: "Questions to try" });
    const asked = within(questions)
      .getAllByRole("listitem")
      .map((item) => item.textContent);
    expect(asked).toHaveLength(3);
    expect(asked.every((question) => question.endsWith("?"))).toBe(true);
  });

  it("renders synchronously and fetches nothing, so the route is static", () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");

    const element = HomePage();
    expect(element).not.toBeInstanceOf(Promise);
    render(element);

    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("shows no live or baked-in data: the only figures are fixed facts", () => {
    const { container } = render(<HomePage />);

    // "Formula 1", titles "since 1950" and car telemetry "since 2023" never go stale.
    expect(new Set(readableText(container).match(/\d+/g))).toEqual(new Set(["1", "1950", "2023"]));
  });

  it("draws its illustrations for the eye only, with the racing line clipping a red apex", () => {
    const { container } = render(<HomePage />);

    const apex = container.querySelector("[data-apex]");
    expect(apex?.closest('[aria-hidden="true"]')).not.toBeNull();
    expect(apex).toHaveAttribute("fill", "#e10600");
  });
});
