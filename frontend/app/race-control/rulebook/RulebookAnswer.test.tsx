import { screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { RULEBOOK_2026 } from "@/test/fixtures/rulebook";
import { renderWithProviders } from "@/test/render";

import { RulebookAnswer } from "./RulebookAnswer";

import type { RulebookSearched } from "./rulebookModel";

function show(answer: RulebookSearched, retry = vi.fn()) {
  return { retry, ...renderWithProviders(<RulebookAnswer answer={answer} retry={retry} refreshing={false} />) };
}

describe("an AI-written answer", () => {
  it("shows the heading, the marked-up paragraph and every source, then the note", () => {
    show(RULEBOOK_2026.answered_ai);

    expect(screen.getByText("Answer · AI-written")).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { level: 2, name: "A car that broke parc fermé starts from the pit lane" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Article B3.5.3").tagName).toBe("B");
    const sources = within(screen.getByRole("list")).getAllByRole("listitem");
    expect(sources).toHaveLength(4);
    expect(screen.getAllByText("source").length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText(/Written by AI from the sources below only/)).toBeInTheDocument();
  });

  it("links the decision's FIA document and names the articles it cites", () => {
    show(RULEBOOK_2026.answered_ai);

    const link = screen.getByRole("link", { name: "Document 65" });
    expect(link).toHaveAttribute("href", RULEBOOK_2026.answered_ai.decisions.items[0].url);
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noreferrer");
    expect(link.parentElement).toHaveTextContent("cites B3.4.3, B3.5.3, B3.5.4");
    expect(screen.getByText(/Required to start the Race from the pit lane\./, { selector: "div" })).toBeInTheDocument();
  });

  it("quotes the passages with their article numbers and page", () => {
    show(RULEBOOK_2026.answered_ai);

    expect(screen.getAllByText(/FIA 2026 F1 Regulations · Section B · Sporting · page 29/)).toHaveLength(3);
  });
});

describe("a computed answer", () => {
  it("says it is computed and why", () => {
    show(RULEBOOK_2026.answered_computed);

    expect(screen.getByText("Answer · computed")).toBeInTheDocument();
    expect(screen.getByText(/The AI summary is unavailable just now/)).toBeInTheDocument();
  });

  it("says when the AI text named something the sources do not hold", () => {
    const summary = { ...RULEBOOK_2026.answered_computed.summary, why: "check_failed" as const };
    show({ ...RULEBOOK_2026.answered_computed, summary });

    expect(screen.getByText(/The AI summary named something the sources don't hold/)).toBeInTheDocument();
  });
});

describe("keyword matches", () => {
  it("puts the failure card for the passages above the matches, with a working Retry", async () => {
    const { retry, user } = show(RULEBOOK_2026.keyword);

    expect(screen.getByText("Regulation passages unavailable")).toBeInTheDocument();
    expect(screen.getByText(RULEBOOK_2026.keyword.reason!)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Retry" }));

    expect(retry).toHaveBeenCalledTimes(1);
  });

  it("labels the decisions as keyword matches and quotes no passage", () => {
    show(RULEBOOK_2026.keyword);

    expect(screen.getByText("Stewards' decisions · keyword matches")).toBeInTheDocument();
    expect(screen.getAllByText(/keyword match: /)).toHaveLength(3);
    expect(screen.queryByText(/Regulations · Section/)).not.toBeInTheDocument();
    expect(
      screen.getByText(/not matched to an article of the regulations/, { selector: "p.font-mono" }),
    ).toBeInTheDocument();
  });
});
