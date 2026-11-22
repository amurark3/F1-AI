import { act, renderHook } from "@testing-library/react";
import { createElement } from "react";
import { renderToString } from "react-dom/server";
import { beforeEach, describe, expect, it } from "vitest";

import { useLocalChats } from "./useLocalChats";

import type { Chat } from "./engineerModel";

const KEY = "f1ai_chats";

function seed(chats: Chat[]) {
  window.localStorage.setItem(KEY, JSON.stringify(chats));
}

function stored(): Chat[] {
  return JSON.parse(window.localStorage.getItem(KEY) ?? "[]") as Chat[];
}

const chat = (id: string, updatedAt = 1): Chat => ({
  id,
  title: id,
  updatedAt,
  messages: [{ role: "user", content: "q" }],
});

describe("useLocalChats", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it("starts with the threads stored in this browser", () => {
    seed([chat("a"), chat("b")]);
    const { result } = renderHook(() => useLocalChats());

    expect(result.current.chats.map((c) => c.id)).toEqual(["a", "b"]);
  });

  it.each([["{not json"], ['{"a": 1}']])("reads corrupt storage (%s) as no threads", (raw) => {
    window.localStorage.setItem(KEY, raw);
    const { result } = renderHook(() => useLocalChats());

    expect(result.current.chats).toEqual([]);
  });

  it("creates a thread at the top, titled 'New Chat'", () => {
    seed([chat("a")]);
    const { result } = renderHook(() => useLocalChats());

    let created: Chat | undefined;
    act(() => {
      created = result.current.createChat();
    });

    expect(created?.title).toBe("New Chat");
    expect(result.current.chats.map((c) => c.id)).toEqual([created?.id, "a"]);
  });

  it("adds a message, titles the thread from the first question and moves it to the top", () => {
    seed([chat("a"), { ...chat("b"), title: "New Chat", messages: [] }]);
    const { result } = renderHook(() => useLocalChats());

    act(() => result.current.addMessage("b", { role: "user", content: "Who won in Mexico?" }));
    act(() => result.current.addMessage("b", { role: "assistant", content: "Verstappen." }));

    expect(result.current.chats.map((c) => c.id)).toEqual(["b", "a"]);
    expect(result.current.chats[0].title).toBe("Who won in Mexico?");
    expect(result.current.chats[0].messages).toHaveLength(2);
  });

  it("cuts a long first question to 50 characters", () => {
    seed([{ ...chat("b"), title: "New Chat", messages: [] }]);
    const { result } = renderHook(() => useLocalChats());

    act(() => result.current.addMessage("b", { role: "user", content: "x".repeat(60) }));

    expect(result.current.chats[0].title).toBe(`${"x".repeat(50)}...`);
  });

  it("ignores a message for a thread that is not there", () => {
    seed([chat("a")]);
    const { result } = renderHook(() => useLocalChats());

    act(() => result.current.addMessage("zzz", { role: "user", content: "hi" }));

    expect(stored()).toEqual([chat("a")]);
  });

  it("replaces the last message whole, with its data, and keeps the order", () => {
    seed([chat("a"), chat("b")]);
    const { result } = renderHook(() => useLocalChats());
    const data = { subject: "2026 calendar", sources: ["f1db"], charts: [] };

    act(() => result.current.updateLastMessage("b", { role: "assistant", content: "Done.", data }));

    expect(stored().map((c) => c.id)).toEqual(["a", "b"]);
    expect(stored()[1].messages).toEqual([{ role: "assistant", content: "Done.", data }]);
  });

  it("does nothing to an unknown or empty thread when updating its last message", () => {
    seed([{ ...chat("a"), messages: [] }]);
    const { result } = renderHook(() => useLocalChats());

    act(() => result.current.updateLastMessage("a", { role: "assistant", content: "x" }));
    act(() => result.current.updateLastMessage("zzz", { role: "assistant", content: "x" }));

    expect(stored()[0].messages).toEqual([]);
  });

  it("replaces a thread's messages", () => {
    seed([chat("a"), chat("b")]);
    const { result } = renderHook(() => useLocalChats());

    act(() => result.current.setMessages("b", []));

    expect(stored().map((c) => c.messages.length)).toEqual([1, 0]);
  });

  it("deletes a thread and returns it with its place; null for an unknown id", () => {
    seed([chat("a"), chat("b"), chat("c")]);
    const { result } = renderHook(() => useLocalChats());

    let removed: ReturnType<typeof result.current.deleteChat> | undefined;
    let missing: ReturnType<typeof result.current.deleteChat> | undefined;
    act(() => {
      removed = result.current.deleteChat("b");
      missing = result.current.deleteChat("zzz");
    });

    expect(removed).toEqual({ chat: chat("b"), index: 1 });
    expect(missing).toBeNull();
    expect(stored().map((c) => c.id)).toEqual(["a", "c"]);
  });

  it("restores a deleted thread at its place, or at the end when the list is shorter", () => {
    seed([chat("a"), chat("c")]);
    const { result } = renderHook(() => useLocalChats());

    act(() => result.current.restoreChat(chat("b"), 1));
    expect(stored().map((c) => c.id)).toEqual(["a", "b", "c"]);

    act(() => result.current.restoreChat(chat("z"), 99));
    expect(stored().map((c) => c.id)).toEqual(["a", "b", "c", "z"]);
  });

  it("renders no threads on the server, which has no storage", () => {
    seed([chat("a")]);
    function Count() {
      return String(useLocalChats().chats.length);
    }

    expect(renderToString(createElement(Count))).toBe("0");
  });

  it("reads another tab's change", () => {
    const { result } = renderHook(() => useLocalChats());
    expect(result.current.chats).toEqual([]);

    act(() => {
      seed([chat("a")]);
      window.dispatchEvent(new StorageEvent("storage", { key: KEY }));
    });

    expect(result.current.chats.map((c) => c.id)).toEqual(["a"]);
  });
});
