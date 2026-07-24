"use client";

import { useState, useRef, useEffect, useCallback, type Dispatch, type RefObject, type SetStateAction } from "react";

import { API_BASE } from "../constants/api";
import { getErrorMessage } from "../utils/errors";

import { useLocalChats, type Chat, type Message } from "./useLocalChats";

const USER_ID_KEY = "f1ai_user_id";

/** Stable per-browser user id (localStorage), created lazily on first send. */
function getOrCreateUserId(): string {
  if (typeof window === "undefined") return "anonymous";
  try {
    let id = window.localStorage.getItem(USER_ID_KEY);
    if (!id) {
      id = `u_${crypto.randomUUID()}`;
      window.localStorage.setItem(USER_ID_KEY, id);
    }
    return id;
  } catch {
    return "anonymous";
  }
}

interface StreamCallbacks {
  onToken: (fullContent: string) => void;
  onToolStatus: (name: string | null) => void;
}

/** Read the chat stream, stripping `[TOOL_*]` markers into status updates. */
async function readChatStream(
  body: ReadableStream<Uint8Array>,
  { onToken, onToolStatus }: StreamCallbacks,
): Promise<string> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let assistantContent = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    const chunk = decoder.decode(value, { stream: true });

    // Format: [TOOL_START]Tool Name[/TOOL_START] and [TOOL_END]Tool Name[/TOOL_END]
    const remaining = chunk
      .replace(/\[TOOL_START\](.*?)\[\/TOOL_START\]/g, (_, name: string) => {
        onToolStatus(name);
        return "";
      })
      .replace(/\[TOOL_END\](.*?)\[\/TOOL_END\]/g, () => {
        onToolStatus(null);
        return "";
      });

    if (remaining) {
      assistantContent += remaining;
      onToken(assistantContent);
    }
  }

  return assistantContent;
}

interface ChatActionContext {
  activeChatId: string | null;
  messages: Message[];
  createChat: () => Chat;
  addMessage: (chatId: string, message: Message) => void;
  updateLastMessage: (chatId: string, content: string) => void;
  setActiveChatId: Dispatch<SetStateAction<string | null>>;
  setMessages: Dispatch<SetStateAction<Message[]>>;
  setInput: Dispatch<SetStateAction<string>>;
  setIsLoading: Dispatch<SetStateAction<boolean>>;
  setToolStatus: Dispatch<SetStateAction<string | null>>;
}

/** Append the user's message, stream the assistant reply, and persist both. */
async function sendChatMessage(text: string, ctx: ChatActionContext): Promise<void> {
  let chatId = ctx.activeChatId;
  if (!chatId) {
    const chat = ctx.createChat();
    chatId = chat.id;
    ctx.setActiveChatId(chatId);
  }

  const userMessage: Message = { role: "user", content: text };
  ctx.setMessages((prev) => [...prev, userMessage]);
  ctx.addMessage(chatId, userMessage);
  ctx.setInput("");
  ctx.setIsLoading(true);

  try {
    const response = await fetch(`${API_BASE}/api/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        messages: [...ctx.messages, userMessage],
        // Stable client id (localStorage) unlocks server-side personalisation
        // and cross-session memory; the chat id scopes the conversation thread.
        user_id: getOrCreateUserId(),
        thread_id: chatId,
      }),
    });

    if (!response.ok) throw new Error(`Server error: ${response.status}`);
    if (!response.body) throw new Error("No response stream received.");

    const emptyAssistant: Message = { role: "assistant", content: "" };
    ctx.setMessages((prev) => [...prev, emptyAssistant]);
    ctx.addMessage(chatId, emptyAssistant);

    const assistantContent = await readChatStream(response.body, {
      onToken: (content) =>
        ctx.setMessages((prev) => {
          const updated = [...prev];
          updated[updated.length - 1] = { role: "assistant", content };
          return updated;
        }),
      onToolStatus: ctx.setToolStatus,
    });

    ctx.updateLastMessage(chatId, assistantContent);
  } catch (error) {
    console.error("Chat error:", error);
    const errMsg = `**Connection Error:** Could not reach the backend. Make sure the server is running.\n\n_${getErrorMessage(error)}_`;
    ctx.setMessages((prev) => [...prev, { role: "assistant", content: errMsg }]);
    ctx.addMessage(chatId, { role: "assistant", content: errMsg });
  } finally {
    ctx.setIsLoading(false);
    ctx.setToolStatus(null);
  }
}

/** Most recent user message content, or null when none exists. */
function findLastUserMessage(messages: Message[]): string | null {
  for (let i = messages.length - 1; i >= 0; i--) {
    if (messages[i].role === "user") return messages[i].content;
  }
  return null;
}

interface RegenerateContext {
  isLoading: boolean;
  messages: Message[];
  setMessages: Dispatch<SetStateAction<Message[]>>;
  sendMessage: (text: string) => Promise<void>;
}

/** Drop the trailing assistant + user turn and re-send the last user prompt. */
async function regenerateLastMessage(ctx: RegenerateContext): Promise<void> {
  if (ctx.isLoading || ctx.messages.length < 2) return;
  const lastUserMsg = findLastUserMessage(ctx.messages);
  if (!lastUserMsg) return;

  // Remove trailing assistant message(s), then the last user message —
  // sendMessage re-adds the user turn along with a fresh assistant response.
  ctx.setMessages((prev) => {
    const trimmed = [...prev];
    while (trimmed.length > 0 && trimmed[trimmed.length - 1].role === "assistant") {
      trimmed.pop();
    }
    return trimmed;
  });
  ctx.setMessages((prev) => (prev.length > 0 && prev[prev.length - 1].role === "user" ? prev.slice(0, -1) : prev));

  await ctx.sendMessage(lastUserMsg);
}

interface ThreadActionParams {
  chats: Chat[];
  activeChatId: string | null;
  deleteChat: (id: string) => void;
  setActiveChatId: Dispatch<SetStateAction<string | null>>;
  setMessages: Dispatch<SetStateAction<Message[]>>;
  setInput: Dispatch<SetStateAction<string>>;
  setSidebarOpen: Dispatch<SetStateAction<boolean>>;
}

/** New/select/delete handlers for chat threads, memoised for stable identity. */
function useChatThreadActions({
  chats,
  activeChatId,
  deleteChat,
  setActiveChatId,
  setMessages,
  setInput,
  setSidebarOpen,
}: ThreadActionParams) {
  const handleNewChat = useCallback(() => {
    setActiveChatId(null);
    setMessages([]);
    setInput("");
    setSidebarOpen(false);
  }, [setActiveChatId, setMessages, setInput, setSidebarOpen]);

  const handleSelectChat = useCallback(
    (id: string) => {
      const chat = chats.find((c) => c.id === id);
      if (chat) {
        setActiveChatId(id);
        setMessages(chat.messages);
      }
    },
    [chats, setActiveChatId, setMessages],
  );

  const handleDeleteChat = useCallback(
    (id: string) => {
      deleteChat(id);
      if (activeChatId === id) {
        setActiveChatId(null);
        setMessages([]);
      }
    },
    [activeChatId, deleteChat, setActiveChatId, setMessages],
  );

  return { handleNewChat, handleSelectChat, handleDeleteChat };
}

/**
 * Reset the working message list from the persisted thread when the active id
 * changes. Adjusting state during render is React's recommended alternative to a
 * state-syncing effect — it avoids the extra commit and cascading re-render.
 */
function useSyncedThreadMessages(
  activeChatId: string | null,
  activeChat: Chat | null,
  setMessages: Dispatch<SetStateAction<Message[]>>,
) {
  const [syncedChatId, setSyncedChatId] = useState<string | null>(activeChatId);
  if (activeChatId !== syncedChatId) {
    setSyncedChatId(activeChatId);
    if (activeChat) {
      setMessages(activeChat.messages);
    }
  }
}

/** Auto-scroll to the latest message and refocus the input once a response completes. */
function useChatViewEffects(
  messagesEndRef: RefObject<HTMLDivElement | null>,
  inputRef: RefObject<HTMLInputElement | null>,
  messages: Message[],
  isLoading: boolean,
) {
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messagesEndRef, messages]);

  useEffect(() => {
    if (!isLoading) inputRef.current?.focus();
  }, [inputRef, isLoading]);
}

export function useChat() {
  const { chats, createChat, deleteChat, addMessage, updateLastMessage } = useLocalChats();

  const [activeChatId, setActiveChatId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [toolStatus, setToolStatus] = useState<string | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(true);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const activeChat = chats.find((c) => c.id === activeChatId) ?? null;

  useSyncedThreadMessages(activeChatId, activeChat, setMessages);
  useChatViewEffects(messagesEndRef, inputRef, messages, isLoading);

  const { handleNewChat, handleSelectChat, handleDeleteChat } = useChatThreadActions({
    chats,
    activeChatId,
    deleteChat,
    setActiveChatId,
    setMessages,
    setInput,
    setSidebarOpen,
  });

  const sendMessage = useCallback(
    (text: string) =>
      sendChatMessage(text, {
        activeChatId,
        messages,
        createChat,
        addMessage,
        updateLastMessage,
        setActiveChatId,
        setMessages,
        setInput,
        setIsLoading,
        setToolStatus,
      }),
    [activeChatId, messages, createChat, addMessage, updateLastMessage],
  );

  const handleSubmit = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();
      if (!input.trim()) return;
      await sendMessage(input.trim());
    },
    [input, sendMessage],
  );

  const regenerate = useCallback(
    () => regenerateLastMessage({ isLoading, messages, setMessages, sendMessage }),
    [isLoading, messages, sendMessage],
  );

  return {
    // State
    chats,
    activeChatId,
    activeChat,
    messages,
    input,
    isLoading,
    toolStatus,
    sidebarOpen,
    sidebarCollapsed,

    // Refs
    messagesEndRef,
    inputRef,

    // Actions
    setInput,
    setSidebarOpen,
    setSidebarCollapsed,
    sendMessage,
    handleSubmit,
    handleNewChat,
    handleSelectChat,
    handleDeleteChat,
    regenerate,
  };
}
