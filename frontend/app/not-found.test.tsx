import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import NotFound from "./not-found";
import { NAV_GROUPS, NAV_LINKS } from "./ui/shell/navConfig";

const wayBack = () => screen.getByRole("navigation", { name: "All screens" });

describe("the 404 page", () => {
  it("says the page is missing, in its one heading", () => {
    render(<NotFound />);

    expect(screen.getByText("Error 404")).toBeInTheDocument();
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Page not found");
  });

  it("offers every screen from the nav config as a way back, numbered in the menu's order", () => {
    render(<NotFound />);

    const links = within(wayBack()).getAllByRole("link");
    const screens = NAV_LINKS;
    expect(links).toHaveLength(screens.length);
    screens.forEach(({ label, href }, i) => {
      expect(links[i]).toHaveAttribute("href", href);
      expect(links[i]).toHaveTextContent(`${String(i + 1).padStart(2, "0")}${label}`);
      // No screen is the current one on a page that doesn't exist.
      expect(links[i]).not.toHaveAttribute("aria-current");
    });
  });

  it("lists the same categories as the drawer", () => {
    render(<NotFound />);

    expect(
      within(wayBack())
        .getAllByRole("heading")
        .map((heading) => heading.textContent),
    ).toEqual(NAV_GROUPS.map(({ label }) => label));
  });
});
