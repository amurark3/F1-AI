import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { AnswerMarkdown } from "./AnswerMarkdown";

const TABLE = [
  "| Pos | Driver | Pts |",
  "| :-- | :----- | --: |",
  "| 1 | Antonelli | 25 |",
  "| 2 | Verstappen | 18 |",
].join("\n");

describe("AnswerMarkdown", () => {
  it("renders prose, emphasis and the headings demoted below the page's h1", () => {
    render(<AnswerMarkdown content={"# Title\n\n## Next\n\n### Small\n\nSome **bold** and *slanted* text."} />);

    expect(screen.getByRole("heading", { level: 3, name: "Title" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 3, name: "Next" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 4, name: "Small" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { level: 1 })).toBeNull();
    expect(screen.getByText("bold")).toHaveClass("font-semibold", "text-rc-ink");
    expect(screen.getByText("slanted").tagName).toBe("EM");
  });

  it("renders lists, a link that opens safely, a quote, a rule, code and a code block", () => {
    render(
      <AnswerMarkdown
        content={[
          "- one",
          "- two",
          "",
          "1. first",
          "2. second",
          "",
          "[the FIA](https://www.fia.com/)",
          "",
          "> a quote",
          "",
          "---",
          "",
          "Use `DRS` here.",
          "",
          "```",
          "block of code",
          "```",
        ].join("\n")}
      />,
    );

    expect(screen.getAllByRole("list")).toHaveLength(2);
    const link = screen.getByRole("link", { name: "the FIA" });
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
    expect(screen.getByText("a quote").closest("blockquote")).toBeInTheDocument();
    expect(screen.getByRole("separator")).toBeInTheDocument();
    expect(screen.getByText("DRS").tagName).toBe("CODE");
    expect(screen.getByText("block of code").closest("pre")).toBeInTheDocument();
  });

  it("renders a table in its own scrolling box, with a right-aligned column in mono", () => {
    render(<AnswerMarkdown content={TABLE} />);

    const table = screen.getByRole("table");
    expect(table.parentElement).toHaveClass("overflow-x-auto", "rounded-md");
    expect(within(table).getAllByRole("columnheader")).toHaveLength(3);
    expect(screen.getByRole("columnheader", { name: "Pts" })).toHaveClass("text-right", "font-mono");
    expect(screen.getByRole("cell", { name: "25" })).toHaveClass("text-right", "font-mono");
    expect(screen.getByRole("cell", { name: "Antonelli" })).not.toHaveClass("text-right");
  });

  it("does not render raw HTML from the model", () => {
    const { container } = render(<AnswerMarkdown content={'Hello <script>alert(1)</script><b onclick="x()">no</b>'} />);

    expect(container.querySelector("script")).toBeNull();
    expect(container.querySelector("b")).toBeNull();
  });
});
