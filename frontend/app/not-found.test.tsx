import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import NotFound from "./not-found";
import { MORE_NAV, PRIMARY_NAV } from "./ui/shell/navConfig";

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
    const screens = [...PRIMARY_NAV, ...MORE_NAV];
    expect(links).toHaveLength(screens.length);
    screens.forEach(({ label, href }, i) => {
      expect(links[i]).toHaveAttribute("href", href);
      expect(links[i]).toHaveTextContent(`${String(i + 1).padStart(2, "0")}${label}`);
      // No screen is the current one on a page that doesn't exist.
      expect(links[i]).not.toHaveAttribute("aria-current");
    });
  });

  it("keeps the More screens under their own label, as the menu does", () => {
    render(<NotFound />);

    const lists = within(wayBack()).getAllByRole("list");
    expect(lists).toHaveLength(2);
    expect(
      within(lists[1])
        .getAllByRole("link")
        .map((link) => link.getAttribute("href")),
    ).toEqual(MORE_NAV.map(({ href }) => href));
    expect(within(wayBack()).getByText("More")).toBeInTheDocument();
  });
});
