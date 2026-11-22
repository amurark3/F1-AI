import { useCallback, useSyncExternalStore } from "react";

import type { Chat, Message } from "./engineerModel";

const STORAGE_KEY = "f1ai_chats";
const MAX_TITLE_LENGTH = 50;

/** Stable empty reference — required so `getSnapshot` never returns a new array. */
const NO_CHATS: Chat[] = [];

const listeners = new Set<() => void>();

/** Cached parse of the raw localStorage string, keyed by that string. */
let cachedRaw: string | null = null;
let cachedChats: Chat[] = NO_CHATS;

function parseChats(raw: string | null): Chat[] {
  if (!raw) return NO_CHATS;
  try {
    const parsed: unknown = JSON.parse(raw);
    return Array.isArray(parsed) ? (parsed as Chat[]) : NO_CHATS;
  } catch {
    return NO_CHATS;
  }
}

/**
 * `useSyncExternalStore` requires a referentially stable snapshot, so the
 * parsed value is memoised against the raw string it came from.
 */
function getSnapshot(): Chat[] {
  const raw = localStorage.getItem(STORAGE_KEY);
  if (raw !== cachedRaw) {
    cachedRaw = raw;
    cachedChats = parseChats(raw);
  }
  return cachedChats;
}

/** The server has no localStorage; React also uses this for the hydration render. */
function getServerSnapshot(): Chat[] {
  return NO_CHATS;
}

function subscribe(onStoreChange: () => void): () => void {
  listeners.add(onStoreChange);
  window.addEventListener("storage", onStoreChange);
  return () => {
    listeners.delete(onStoreChange);
    window.removeEventListener("storage", onStoreChange);
  };
}

function writeChats(chats: Chat[]): void {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(chats));
  for (const listener of listeners) listener();
}

function titleFor(chat: Chat, msg: Message): string {
  if (chat.title !== "New Chat" || msg.role !== "user") return chat.title;
  const head = msg.content.slice(0, MAX_TITLE_LENGTH);
  return msg.content.length > MAX_TITLE_LENGTH ? `${head}...` : head;
}

/** The threads in this browser (`f1ai_chats`), newest first; every change writes a new list. */
export function useLocalChats() {
  const chats = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);

  const createChat = useCallback((): Chat => {
    const chat: Chat = { id: crypto.randomUUID(), title: "New Chat", updatedAt: Date.now(), messages: [] };
    writeChats([chat, ...getSnapshot()]);
    return chat;
  }, []);

  /** Removes a thread and hands back what it removed, with its place in the list; `null` for an unknown id. */
  const deleteChat = useCallback((id: string): { chat: Chat; index: number } | null => {
    const all = getSnapshot();
    const index = all.findIndex((c) => c.id === id);
    if (index === -1) return null;
    writeChats(all.filter((_, i) => i !== index));
    return { chat: all[index], index };
  }, []);

  /** Puts a deleted thread back at its place, or at the end if the list is shorter now. */
  const restoreChat = useCallback((chat: Chat, index: number) => {
    const all = getSnapshot();
    const at = Math.min(index, all.length);
    writeChats([...all.slice(0, at), chat, ...all.slice(at)]);
  }, []);

  const addMessage = useCallback((chatId: string, msg: Message) => {
    const all = getSnapshot();
    const idx = all.findIndex((c) => c.id === chatId);
    if (idx === -1) return;
    const chat = all[idx];
    const updated: Chat = {
      ...chat,
      messages: [...chat.messages, msg],
      title: titleFor(chat, msg),
      updatedAt: Date.now(),
    };
    // The thread that just changed moves to the top of the list.
    writeChats([updated, ...all.filter((_, i) => i !== idx)]);
  }, []);

  /** Replaces the thread's last message whole. Streaming keeps list order, so this does not re-sort. */
  const updateLastMessage = useCallback((chatId: string, message: Message) => {
    const all = getSnapshot();
    const chat = all.find((c) => c.id === chatId);
    if (!chat || chat.messages.length === 0) return;
    writeChats(
      all.map((c) =>
        c.id === chatId ? { ...c, messages: [...c.messages.slice(0, -1), message], updatedAt: Date.now() } : c,
      ),
    );
  }, []);

  /** Replaces a thread's messages (regenerate drops the answer it is replacing). */
  const setMessages = useCallback((chatId: string, messages: Message[]) => {
    writeChats(getSnapshot().map((c) => (c.id === chatId ? { ...c, messages } : c)));
  }, []);

  return { chats, createChat, deleteChat, restoreChat, addMessage, updateLastMessage, setMessages };
}
