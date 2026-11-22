import { screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { renderWithProviders } from "@/test/render";

import { ChatHistory } from "./ChatHistory";
import { useChat } from "./useChat";

import type { Chat } from "./engineerModel";

const NOW = new Date(2026, 10, 22, 15, 0).getTime();
const HOUR = 3_600_000;

function chat(id: string, title: string, updatedAt: number): Chat {
  return { id, title, updatedAt, messages: [{ role: "user", content: title }] };
}

const SEEDED = [
  chat("a", "Who won in Mexico?", NOW - HOUR),
  chat("b", "Parc fermé rules", NOW - 2 * HOUR),
  chat("c", "Tyre degradation at Interlagos", NOW - 3 * 86_400_000),
];

/** The rail wired to the chat hook, as the page wires it. */
function Rail() {
  const chatState = useChat();
  return (
    <>
      <ChatHistory
        chats={chatState.chats}
        activeChatId={chatState.activeChatId}
        deleted={chatState.deleted?.chat ?? null}
        onNewChat={chatState.handleNewChat}
        onSelectChat={chatState.handleSelectChat}
        onDeleteChat={chatState.handleDeleteChat}
        onUndoDelete={chatState.undoDelete}
      />
      <output data-testid="open">{chatState.activeChatId}</output>
    </>
  );
}

/** The titles of a group's thread rows, in order (the × buttons are named "Delete thread: …"). */
function rowTitles(group: HTMLElement): Array<string | null> {
  return within(group)
    .getAllByRole("button", { name: /^(?!Delete)/ })
    .map((button) => button.textContent);
}

describe("ChatHistory", () => {
  beforeEach(() => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(NOW);
    window.localStorage.setItem("f1ai_chats", JSON.stringify(SEEDED));
  });

  afterEach(() => {
    vi.useRealTimers();
    window.localStorage.clear();
  });

  it("groups the threads under Today and Earlier, newest first, with New question above", () => {
    renderWithProviders(<Rail />);

    expect(screen.getByRole("button", { name: "New question" })).toBeInTheDocument();
    const today = screen.getByRole("region", { name: "Today" });
    const earlier = screen.getByRole("region", { name: "Earlier" });
    expect(rowTitles(today)).toEqual(["Who won in Mexico?", "Parc fermé rules"]);
    expect(within(earlier).getByRole("button", { name: "Tyre degradation at Interlagos" })).toBeInTheDocument();
  });

  it("is only the New question button when there are no threads", () => {
    window.localStorage.clear();
    renderWithProviders(<Rail />);

    expect(screen.getByRole("button", { name: "New question" })).toBeInTheDocument();
    expect(screen.queryByRole("region")).toBeNull();
    expect(screen.queryByRole("button", { name: /History/ })).toBeNull();
  });

  it("marks the open thread, which opens on a press", async () => {
    const { user } = renderWithProviders(<Rail />);

    await user.click(screen.getByRole("button", { name: "Parc fermé rules" }));

    expect(screen.getByRole("button", { name: "Parc fermé rules" })).toHaveAttribute("aria-current", "true");
    expect(screen.getByRole("button", { name: "Who won in Mexico?" })).not.toHaveAttribute("aria-current");
    expect(screen.getByTestId("open")).toHaveTextContent("b");
  });

  it("deletes a thread with no confirm, and an undo line takes its place until Undo puts it back", async () => {
    const { user } = renderWithProviders(<Rail />);

    await user.click(screen.getByRole("button", { name: "Delete thread: Who won in Mexico?" }));

    expect(screen.queryByRole("button", { name: "Who won in Mexico?" })).toBeNull();
    const today = screen.getByRole("region", { name: "Today" });
    expect(within(today).getByText("Deleted · Who won in Mexico?")).toBeInTheDocument();
    expect(JSON.parse(window.localStorage.getItem("f1ai_chats") ?? "[]")).toHaveLength(2);

    await user.click(screen.getByRole("button", { name: "Undo" }));

    expect(screen.queryByText(/^Deleted/)).toBeNull();
    expect(rowTitles(screen.getByRole("region", { name: "Today" }))).toEqual([
      "Who won in Mexico?",
      "Parc fermé rules",
    ]);
    expect(JSON.parse(window.localStorage.getItem("f1ai_chats") ?? "[]")).toHaveLength(3);
  });

  it("closes the thread that is open when it is deleted", async () => {
    const { user } = renderWithProviders(<Rail />);
    await user.click(screen.getByRole("button", { name: "Parc fermé rules" }));

    await user.click(screen.getByRole("button", { name: "Delete thread: Parc fermé rules" }));

    expect(screen.getByTestId("open")).toBeEmptyDOMElement();
  });

  it("shows one undo line: a second delete replaces the first, and New question clears it", async () => {
    const { user } = renderWithProviders(<Rail />);

    await user.click(screen.getByRole("button", { name: "Delete thread: Who won in Mexico?" }));
    await user.click(screen.getByRole("button", { name: "Delete thread: Parc fermé rules" }));

    expect(screen.getAllByText(/^Deleted/)).toHaveLength(1);
    expect(screen.getByText("Deleted · Parc fermé rules")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "New question" }));

    expect(screen.queryByText(/^Deleted/)).toBeNull();
  });

  it("on a phone opens the list from a History · n toggle, and closes it when a thread is chosen", async () => {
    const { user } = renderWithProviders(<Rail />);
    const toggle = screen.getByRole("button", { name: "History · 3" });
    const list = document.getElementById("engineer-history");

    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(toggle).toHaveAttribute("aria-controls", "engineer-history");
    expect(list).toHaveClass("hidden", "md:block");

    await user.click(toggle);

    expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect(list).toHaveClass("block");
    expect(list).not.toHaveClass("hidden");

    await user.click(screen.getByRole("button", { name: "Who won in Mexico?" }));

    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(list).toHaveClass("hidden");
  });
});
