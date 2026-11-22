import { act, screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useServerStatus, type ServerState } from "@/app/hooks/useServerStatus";
import { DIRECTORY_2026, OVERVIEW_SEGMENTS_2026 } from "@/test/fixtures";
import { apiUrl, server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";

import { EngineerView } from "./EngineerView";

import type { AnswerData, Chat } from "./engineerModel";

vi.mock("@/app/hooks/useServerStatus", () => ({ useServerStatus: vi.fn() }));

const CHAT_URL = apiUrl("/api/chat");
const NOW = new Date(2026, 10, 22, 15, 0).getTime();

/** The mockup's answer data: the fight for second after round 19, four races and no sprint left (100 points). */
const DATA: AnswerData = {
  subject: "2026 standings after round 19",
  sources: ["f1db v2026.19.0 · standings after R19", "4 races left · 100 pts max"],
  charts: [
    {
      kind: "reach",
      title: "2 drivers can still finish second · points after round 19 → most possible",
      championship: "drivers",
      year: 2026,
      rows: [
        { key: "VER", name: "Max Verstappen", team: "Red Bull", points: 261, max: 361 },
        { key: "HAM", name: "Lewis Hamilton", team: "Ferrari", points: 259, max: 359 },
      ],
    },
  ],
};

const encoder = new TextEncoder();

/** An answer the test feeds chunk by chunk, so it can look at the page between chunks. */
function liveAnswer() {
  let controller!: ReadableStreamDefaultController<Uint8Array>;
  const stream = new ReadableStream<Uint8Array>({
    start(c) {
      controller = c;
    },
  });
  return {
    response: () => new HttpResponse(stream, { headers: { "Content-Type": "text/plain" } }),
    push: async (text: string) => {
      await act(() => {
        controller.enqueue(encoder.encode(text));
        return Promise.resolve();
      });
    },
    end: async () => {
      await act(() => {
        controller.close();
        return Promise.resolve();
      });
    },
  };
}

function textAnswer(text: string) {
  return () => new HttpResponse(text, { headers: { "Content-Type": "text/plain" } });
}

interface Sent {
  messages: Array<{ role: string; content: string }>;
  user_id: string;
  thread_id: string;
}

/** Serves `/api/chat` with `answers` in turn, recording each request body. */
function serveChat(...answers: Array<() => Response>): Sent[] {
  const sent: Sent[] = [];
  let turn = 0;
  server.use(
    http.post(CHAT_URL, async ({ request }) => {
      sent.push((await request.json()) as Sent);
      return answers[Math.min(turn++, answers.length - 1)]();
    }),
  );
  return sent;
}

function seedChats(chats: Chat[]) {
  window.localStorage.setItem("f1ai_chats", JSON.stringify(chats));
}

function storedChats(): Chat[] {
  return JSON.parse(window.localStorage.getItem("f1ai_chats") ?? "[]") as Chat[];
}

async function ask(user: ReturnType<typeof renderWithProviders>["user"], text: string) {
  await user.type(screen.getByRole("textbox", { name: "Ask the AI Engineer" }), `${text}{Enter}`);
}

describe("EngineerView", () => {
  beforeEach(() => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(NOW);
    Element.prototype.scrollIntoView = vi.fn();
    vi.mocked(useServerStatus).mockReturnValue({ status: "ready" } as ServerState);
    server.use(
      http.get(apiUrl("/api/profiles/:year/directory"), () => HttpResponse.json(DIRECTORY_2026)),
      http.get(apiUrl("/api/race-control/overview/2026/shell"), () => HttpResponse.json(OVERVIEW_SEGMENTS_2026.shell)),
    );
  });

  afterEach(() => {
    vi.useRealTimers();
    window.localStorage.clear();
  });

  it("opens on the AI Engineer title, the starter prompts, the input, the note and the disclaimer", async () => {
    renderWithProviders(<EngineerView />);

    expect(screen.getByRole("heading", { level: 1, name: "AI Engineer" })).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: /Who does the model favour/ })).toBeVisible();
    expect(screen.getByRole("textbox", { name: "Ask the AI Engineer" })).toHaveFocus();
    expect(screen.getByText(/Answers are built from the same data the screens use/)).toBeInTheDocument();
    expect(screen.getByText(/unofficial and is not associated/i)).toBeInTheDocument();
  });

  it("streams an answer: the tool it runs, then its subject, prose, chart and source chips", async () => {
    const live = liveAnswer();
    const sent = serveChat(live.response);
    const { user } = renderWithProviders(<EngineerView />);

    await ask(user, "Who can finish second?");

    expect(await screen.findByText("Engineer · Working on it")).toBeInTheDocument();
    await live.push("[TOOL_START]Get Driver Standings[/TOOL_START]");
    expect(await screen.findByText("Engineer · Running Get Driver Standings")).toBeInTheDocument();
    await live.push("[TOOL_END]Get Driver Standings[/TOOL_END]");
    const block = `[ANSWER_DATA]${JSON.stringify(DATA)}[/ANSWER_DATA]`;
    await live.push(block.slice(0, 70));
    await live.push(`${block.slice(70)}Verstappen and Hamilton are`);
    await live.push(" still in the fight for second.");
    await live.end();

    expect(await screen.findByText("Engineer · 2026 standings after round 19")).toBeInTheDocument();
    expect(screen.getByText("Verstappen and Hamilton are still in the fight for second.")).toBeInTheDocument();
    const caption = DATA.charts[0].title;
    expect(screen.getByRole("figure")).toHaveTextContent(caption);
    const chart = within(screen.getByRole("list", { name: caption }));
    expect(await chart.findByText("Verstappen")).toBeInTheDocument();
    expect(chart.getAllByRole("listitem")[0]).toHaveTextContent("261 → 361");
    expect(document.querySelectorAll("[data-reach]")).toHaveLength(2);
    const chips = within(screen.getByRole("list", { name: "Sources" })).getAllByRole("listitem");
    expect(chips.map((chip) => chip.textContent)).toEqual(DATA.sources);

    expect(sent[0].messages).toEqual([{ role: "user", content: "Who can finish second?" }]);
    expect(sent[0].thread_id).toBe(storedChats()[0].id);
    expect(storedChats()[0].messages[1]).toEqual({
      role: "assistant",
      content: "Verstappen and Hamilton are still in the fight for second.",
      data: DATA,
    });
  });

  it("sends the thread so far as role and content only, never the stored data", async () => {
    const sent = serveChat(
      textAnswer(`[ANSWER_DATA]${JSON.stringify(DATA)}[/ANSWER_DATA]First.`),
      textAnswer("Second."),
    );
    const { user } = renderWithProviders(<EngineerView />);

    await ask(user, "One");
    await screen.findByText("First.");
    await ask(user, "Two");
    await screen.findByText("Second.");

    expect(sent[1].messages).toEqual([
      { role: "user", content: "One" },
      { role: "assistant", content: "First." },
      { role: "user", content: "Two" },
    ]);
  });

  it("headed an answer that read no tool with the engineer alone, and no chips", async () => {
    serveChat(textAnswer("Hello there."));
    const { user } = renderWithProviders(<EngineerView />);

    await ask(user, "Hi");

    expect(await screen.findByText("Hello there.")).toBeInTheDocument();
    expect(screen.getByText("Engineer")).toBeInTheDocument();
    expect(screen.queryByRole("list", { name: "Sources" })).toBeNull();
    expect(screen.queryByRole("figure")).toBeNull();
  });

  it("groups saved threads under Today and Earlier, opens one, and New question clears the thread", async () => {
    seedChats([
      {
        id: "a",
        title: "Who won in Mexico?",
        updatedAt: NOW - 3_600_000,
        messages: [
          { role: "user", content: "Who won in Mexico?" },
          { role: "assistant", content: "Verstappen won." },
        ],
      },
      {
        id: "b",
        title: "Old question",
        updatedAt: NOW - 5 * 86_400_000,
        messages: [{ role: "user", content: "Old question" }],
      },
    ]);
    const { user } = renderWithProviders(<EngineerView />);

    expect(screen.getByText("Today")).toBeInTheDocument();
    expect(screen.getByText("Earlier")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Who won in Mexico?" }));
    expect(screen.getByText("Verstappen won.")).toBeInTheDocument();
    expect(screen.queryByText(/Start with/)).toBeNull();

    await user.click(screen.getByRole("button", { name: "New question" }));

    expect(screen.queryByText("Verstappen won.")).toBeNull();
    expect(await screen.findByText("Start with")).toBeInTheDocument();
  });

  it("asks a starter question at once", async () => {
    const sent = serveChat(textAnswer("Because of the points."));
    const { user } = renderWithProviders(<EngineerView />);

    await user.click(await screen.findByRole("button", { name: /Can Ferrari still beat Mercedes/ }));

    expect(await screen.findByText("Because of the points.")).toBeInTheDocument();
    expect(sent[0].messages[0].content).toBe("Can Ferrari still beat Mercedes to the constructors' title?");
    expect(screen.queryByText("Start with")).toBeNull();
  });

  describe("when no answer comes", () => {
    it("says the server could not be reached, and Retry asks the same question again", async () => {
      server.use(http.post(CHAT_URL, () => HttpResponse.error()));
      const { user } = renderWithProviders(<EngineerView />);
      await ask(user, "Why?");

      expect(await screen.findByText("Answer unavailable")).toBeInTheDocument();
      expect(screen.getByText("Could not reach the server.")).toBeInTheDocument();
      expect(screen.getAllByText("Why?")).toHaveLength(2); // the question, and the history row

      const sent = serveChat(textAnswer("Because."));
      await user.click(screen.getByRole("button", { name: "Retry" }));

      expect(await screen.findByText("Because.")).toBeInTheDocument();
      expect(screen.queryByText("Answer unavailable")).toBeNull();
      expect(sent[0].messages).toEqual([{ role: "user", content: "Why?" }]);
      expect(storedChats()[0].messages.map((m) => m.role)).toEqual(["user", "assistant"]);
    });

    it("names the status of a server error", async () => {
      server.use(http.post(CHAT_URL, () => HttpResponse.text("no", { status: 500 })));
      const { user } = renderWithProviders(<EngineerView />);

      await ask(user, "Why?");

      expect(await screen.findByText("The server answered 500.")).toBeInTheDocument();
      expect(storedChats()[0].messages).toHaveLength(1);
    });

    it("says so when an answer has no stream", async () => {
      const { user } = renderWithProviders(<EngineerView />);
      vi.spyOn(globalThis, "fetch").mockResolvedValueOnce({ ok: true, body: null } as Response);

      await ask(user, "Why?");

      expect(await screen.findByText("No answer stream was received.")).toBeInTheDocument();
    });

    it("drops a half-written answer when the stream breaks", async () => {
      const broken = new ReadableStream<Uint8Array>({
        start(controller) {
          controller.enqueue(encoder.encode("Half an ans"));
          controller.error(new Error("connection reset"));
        },
      });
      server.use(http.post(CHAT_URL, () => new HttpResponse(broken)));
      const { user } = renderWithProviders(<EngineerView />);

      await ask(user, "Why?");

      expect(await screen.findByText("Could not reach the server.")).toBeInTheDocument();
      expect(screen.queryByText(/Half an ans/)).toBeNull();
      expect(storedChats()[0].messages).toHaveLength(1);
    });
  });

  describe("Regenerate", () => {
    it("is under the latest answer only, and asks the same question again, leaving one answer", async () => {
      const sent = serveChat(textAnswer("First."), textAnswer("Second."), textAnswer("Third."));
      const { user } = renderWithProviders(<EngineerView />);
      await ask(user, "One");
      await screen.findByText("First.");
      await ask(user, "Two");
      await screen.findByText("Second.");

      expect(screen.getAllByRole("button", { name: "Regenerate" })).toHaveLength(1);
      await user.click(screen.getByRole("button", { name: "Regenerate" }));

      expect(await screen.findByText("Third.")).toBeInTheDocument();
      expect(screen.queryByText("Second.")).toBeNull();
      expect(screen.getByText("First.")).toBeInTheDocument();
      expect(sent[2].messages.at(-1)).toEqual({ role: "user", content: "Two" });
      expect(storedChats()[0].messages.map((m) => m.content)).toEqual(["One", "First.", "Two", "Third."]);
      expect(screen.getAllByText("Two")).toHaveLength(1);
    });

    it("is not offered while an answer is on its way", async () => {
      const live = liveAnswer();
      serveChat(textAnswer("First."), live.response);
      const { user } = renderWithProviders(<EngineerView />);
      await ask(user, "One");
      await screen.findByText("First.");

      await ask(user, "Two");

      await screen.findByText("Engineer · Working on it");
      expect(screen.queryByRole("button", { name: "Regenerate" })).toBeNull();
      await live.push("Second.");
      await live.end();
      await waitFor(() => expect(screen.getByRole("button", { name: "Regenerate" })).toBeInTheDocument());
    });
  });
});
