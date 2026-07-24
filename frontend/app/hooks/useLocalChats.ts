import { useCallback, useSyncExternalStore } from "react";

export interface Message {
  role: "user" | "assistant";
  content: string;
}

export interface Chat {
  id: string;
  title: string;
  updatedAt: number;
  messages: Message[];
}

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

function readChats(): Chat[] {
  if (typeof window === "undefined") return NO_CHATS;
  return getSnapshot();
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

export function useLocalChats() {
  const chats = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);

  const createChat = useCallback((): Chat => {
    const chat: Chat = {
      id: crypto.randomUUID(),
      title: "New Chat",
      updatedAt: Date.now(),
      messages: [],
    };
    writeChats([chat, ...readChats()]);
    return chat;
  }, []);

  const deleteChat = useCallback((id: string) => {
    writeChats(readChats().filter((c) => c.id !== id));
  }, []);

  const updateChat = useCallback((id: string, updater: (c: Chat) => Chat) => {
    const all = readChats();
    const idx = all.findIndex((c) => c.id === id);
    if (idx === -1) return;
    const updated: Chat = { ...updater(all[idx]), updatedAt: Date.now() };
    // Move the updated chat to the top of the list.
    writeChats([updated, ...all.filter((_, i) => i !== idx)]);
  }, []);

  const addMessage = useCallback(
    (chatId: string, msg: Message) => {
      updateChat(chatId, (c) => ({
        ...c,
        messages: [...c.messages, msg],
        title: titleFor(c, msg),
      }));
    },
    [updateChat],
  );

  const updateLastMessage = useCallback((chatId: string, content: string) => {
    const all = readChats();
    const chat = all.find((c) => c.id === chatId);
    if (!chat || chat.messages.length === 0) return;
    const lastIdx = chat.messages.length - 1;
    // Streaming updates keep list order stable, so this does not re-sort.
    writeChats(
      all.map((c) =>
        c.id === chatId
          ? {
              ...c,
              messages: c.messages.map((m, i) => (i === lastIdx ? { ...m, content } : m)),
              updatedAt: Date.now(),
            }
          : c,
      ),
    );
  }, []);

  return {
    chats,
    createChat,
    deleteChat,
    addMessage,
    updateLastMessage,
    updateChat,
  };
}
