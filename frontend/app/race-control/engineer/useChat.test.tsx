import { act, renderHook, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { apiUrl, server } from "@/test/msw/server";

import { useChat } from "./useChat";

import type { FormEvent } from "react";

const CHAT_URL = apiUrl("/api/chat");

function submitEvent(): FormEvent {
  return { preventDefault: vi.fn() } as unknown as FormEvent;
}

/** Serves `/api/chat` and records the requests' bodies. */
function serveChat(text = "Answer."): { bodies: unknown[] } {
  const bodies: unknown[] = [];
  server.use(
    http.post(CHAT_URL, async ({ request }) => {
      bodies.push(await request.json());
      return new HttpResponse(text);
    }),
  );
  return { bodies };
}

describe("useChat", () => {
  beforeEach(() => {
    Element.prototype.scrollIntoView = vi.fn();
  });

  afterEach(() => {
    window.localStorage.clear();
  });

  it("ignores what it cannot act on: an unknown thread, an undo with nothing deleted, a regenerate with nothing to redo", async () => {
    const { bodies } = serveChat();
    const { result } = renderHook(() => useChat());

    act(() => result.current.handleSelectChat("zzz"));
    act(() => result.current.handleDeleteChat("zzz"));
    act(() => result.current.undoDelete());
    await act(() => result.current.regenerate());

    expect(result.current.activeChatId).toBeNull();
    expect(result.current.deleted).toBeNull();
    expect(bodies).toEqual([]);
  });

  it("sends nothing for an empty question", async () => {
    const { bodies } = serveChat();
    const { result } = renderHook(() => useChat());

    act(() => result.current.setInput("   "));
    await act(() => result.current.handleSubmit(submitEvent()));

    expect(bodies).toEqual([]);
  });

  it("asks and clears the input, then regenerate with an answer in flight does nothing", async () => {
    const { bodies } = serveChat();
    const { result } = renderHook(() => useChat());

    act(() => result.current.setInput(" Who won? "));
    await act(() => result.current.handleSubmit(submitEvent()));

    expect(bodies).toHaveLength(1);
    expect(result.current.input).toBe("");
    await waitFor(() => expect(result.current.messages.map((m) => m.role)).toEqual(["user", "assistant"]));
  });

  it("falls back to an anonymous user when the browser keeps no id", async () => {
    const { bodies } = serveChat();
    const getItem = window.localStorage.getItem.bind(window.localStorage);
    vi.spyOn(Storage.prototype, "getItem").mockImplementation((key: string) => {
      if (key === "f1ai_user_id") throw new Error("blocked");
      return getItem(key);
    });
    const { result } = renderHook(() => useChat());

    await act(() => result.current.sendMessage("Hi"));

    expect(bodies[0]).toMatchObject({ user_id: "anonymous" });
  });

  it("reports a stream that breaks as unreachable and keeps only the question", async () => {
    const broken = { ok: true, body: { getReader: () => ({ read: () => Promise.reject(new Error("reset")) }) } };
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(broken as unknown as Response);
    const { result } = renderHook(() => useChat());

    await act(() => result.current.sendMessage("Hi"));

    expect(result.current.failure).toBe("Could not reach the server.");
    expect(result.current.messages.map((m) => m.role)).toEqual(["user"]);
  });

  it("keeps the same user id between questions", async () => {
    const { bodies } = serveChat();
    const { result } = renderHook(() => useChat());

    await act(() => result.current.sendMessage("One"));
    await act(() => result.current.sendMessage("Two"));

    const ids = bodies.map((body) => (body as { user_id: string }).user_id);
    expect(ids[0]).toMatch(/^u_/);
    expect(ids[1]).toBe(ids[0]);
  });
});
