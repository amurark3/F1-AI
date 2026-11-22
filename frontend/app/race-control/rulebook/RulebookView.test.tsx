import { screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { RULEBOOK_2026 } from "@/test/fixtures/rulebook";
import { apiUrl, server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";

import { RulebookView } from "./RulebookView";

const SEARCH = apiUrl("/api/race-control/rulebook/search");
const QUESTION = "When is a driver required to start from the pit lane?";

function serve(body: unknown = RULEBOOK_2026.answered_ai, asked: unknown[] = []) {
  server.use(
    http.post(SEARCH, async ({ request }) => {
      asked.push(await request.json());
      return HttpResponse.json(body as Record<string, unknown>);
    }),
  );
  return asked;
}

describe("the Rulebook view", () => {
  it("opens on the title, the box and the quick questions, with nothing searched", () => {
    const asked = serve();
    renderWithProviders(<RulebookView />);

    expect(screen.getByRole("heading", { level: 1, name: "Ask the rulebook" })).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "Question" })).toHaveValue("");
    expect(screen.getAllByRole("button", { name: /\?$/ })).toHaveLength(4);
    expect(screen.queryByText("Answer · AI-written")).not.toBeInTheDocument();
    expect(asked).toEqual([]);
  });

  it("posts the trimmed question and shows the answer", async () => {
    const asked = serve();
    const { user } = renderWithProviders(<RulebookView />);

    await user.type(screen.getByRole("textbox", { name: "Question" }), `  ${QUESTION}  `);
    await user.click(screen.getByRole("button", { name: "Search" }));

    expect(await screen.findByText("Answer · AI-written")).toBeInTheDocument();
    expect(asked).toEqual([{ query: QUESTION }]);
  });

  it("sends nothing for a blank box", async () => {
    const asked = serve();
    const { user } = renderWithProviders(<RulebookView />);

    await user.type(screen.getByRole("textbox", { name: "Question" }), "   ");
    await user.click(screen.getByRole("button", { name: "Search" }));

    expect(asked).toEqual([]);
    expect(screen.queryByLabelText("Answer")).not.toBeInTheDocument();
  });

  it("submits a quick question at once and fills the box with it", async () => {
    const asked = serve();
    const { user } = renderWithProviders(<RulebookView />);

    await user.click(screen.getByRole("button", { name: "How do penalty points work?" }));

    expect(await screen.findByText("Answer · AI-written")).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "Question" })).toHaveValue("How do penalty points work?");
    expect(asked).toEqual([{ query: "How do penalty points work?" }]);
  });

  it("shows a skeleton while a question is out, never the old answer", async () => {
    serve();
    const { user, container } = renderWithProviders(<RulebookView />);
    await user.click(screen.getByRole("button", { name: "What counts as track limits?" }));
    await screen.findByText("Answer · AI-written");
    let release: () => void = () => undefined;
    server.use(
      http.post(SEARCH, async () => {
        await new Promise<void>((resolve) => {
          release = resolve;
        });
        return HttpResponse.json(RULEBOOK_2026.keyword);
      }),
    );

    await user.click(screen.getByRole("button", { name: "How do penalty points work?" }));

    await waitFor(() => expect(container.querySelector("[aria-busy='true']")).not.toBeNull());
    expect(screen.queryByText("Answer · AI-written")).not.toBeInTheDocument();
    release();
    expect(await screen.findByText("Stewards' decisions · keyword matches")).toBeInTheDocument();
  });

  it("explains an HTTP failure and retries the asked question, not the box's text", async () => {
    server.use(http.post(SEARCH, () => new HttpResponse(null, { status: 500 })));
    const { user } = renderWithProviders(<RulebookView />);
    await user.click(screen.getByRole("button", { name: "What counts as track limits?" }));

    expect(await screen.findByText("Answer unavailable")).toBeInTheDocument();
    expect(screen.getByText("The rulebook search failed (HTTP 500).")).toBeInTheDocument();

    const asked = serve();
    await user.type(screen.getByRole("textbox", { name: "Question" }), " edited");
    await user.click(screen.getByRole("button", { name: "Retry" }));

    expect(await screen.findByText("Answer · AI-written")).toBeInTheDocument();
    expect(asked).toEqual([{ query: "What counts as track limits?" }]);
  });

  it("shows the server's reason when nothing could be searched", async () => {
    serve(RULEBOOK_2026.unavailable);
    const { user } = renderWithProviders(<RulebookView />);

    await user.click(screen.getByRole("button", { name: "What counts as track limits?" }));

    expect(await screen.findByText("Answer unavailable")).toBeInTheDocument();
    expect(screen.getByText(RULEBOOK_2026.unavailable.reason!)).toBeInTheDocument();
  });

  it("asks the question again from the passage card's Retry in keyword mode", async () => {
    const asked = serve(RULEBOOK_2026.keyword);
    const { user } = renderWithProviders(<RulebookView />);
    await user.click(screen.getByRole("button", { name: "What counts as track limits?" }));

    await user.click(await screen.findByRole("button", { name: "Retry" }));

    await waitFor(() => expect(asked).toHaveLength(2));
    expect(asked).toEqual([{ query: "What counts as track limits?" }, { query: "What counts as track limits?" }]);
  });
});
