"use client";

import { useCallback, useEffect, useRef, useState, type Dispatch, type RefObject, type SetStateAction } from "react";

import { API_BASE } from "@/app/constants/api";
import { UNREACHABLE_REASON } from "@/app/ui/section/sectionState";

import { parseChatStream, type Chat, type Message, type ParsedStream } from "./engineerModel";
import { useLocalChats } from "./useLocalChats";

const USER_ID_KEY = "f1ai_user_id";

/** Stable per-browser user id (localStorage), created lazily on first send. */
function getOrCreateUserId(): string | null {
  try {
    let id = window.localStorage.getItem(USER_ID_KEY);
    if (!id) {
      id = `u_${crypto.randomUUID()}`;
      window.localStorage.setItem(USER_ID_KEY, id);
    }
    return id;
  } catch {
    return null; // no shared id: without storage the chat simply runs without memory
  }
}

/** The stream's text so far as an assistant message: its prose, and the data its tools read. */
function assistantMessage({ content, data }: ParsedStream): Message {
  return { role: "assistant", content, ...(data ? { data } : {}) };
}

class AnswerFailure extends Error {}

interface ThreadState {
  setMessages: Dispatch<SetStateAction<Message[]>>;
  setToolStatus: Dispatch<SetStateAction<string | null>>;
}

/** Reads the stream chunk by chunk, showing the answer as it grows; returns the finished message. */
async function readAnswer(body: ReadableStream<Uint8Array>, { setMessages, setToolStatus }: ThreadState) {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let raw = "";
  setMessages((prev) => [...prev, { role: "assistant", content: "" }]);
  for (let chunk = await reader.read(); !chunk.done; chunk = await reader.read()) {
    raw += decoder.decode(chunk.value, { stream: true });
    const parsed = parseChatStream(raw, false);
    setToolStatus(parsed.toolStatus);
    setMessages((prev) => [...prev.slice(0, -1), assistantMessage(parsed)]);
  }
  const finished = assistantMessage(parseChatStream(raw, true));
  setMessages((prev) => [...prev.slice(0, -1), finished]);
  return finished;
}

/** Asks the engineer; throws an `AnswerFailure` that says why no answer came. */
async function requestAnswer(history: Message[], chatId: string): Promise<ReadableStream<Uint8Array>> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}/api/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        messages: history.map(({ role, content }) => ({ role, content })),
        // A stable client id unlocks server-side personalisation and memory (null: none); the chat id scopes the thread.
        user_id: getOrCreateUserId(),
        thread_id: chatId,
      }),
    });
  } catch {
    throw new AnswerFailure(UNREACHABLE_REASON);
  }
  if (!response.ok) throw new AnswerFailure(`The server answered ${response.status}.`);
  if (!response.body) throw new AnswerFailure("No answer stream was received.");
  return response.body;
}

/** Keeps the newest message in view, and puts the cursor back in the input when an answer completes. */
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

/**
 * Resets the working message list from the stored thread when the active id
 * changes, during render: React's alternative to a state-syncing effect.
 */
function useSyncedThreadMessages(
  activeChatId: string | null,
  activeChat: Chat | null,
  setMessages: Dispatch<SetStateAction<Message[]>>,
) {
  const [syncedChatId, setSyncedChatId] = useState<string | null>(activeChatId);
  if (activeChatId !== syncedChatId) {
    setSyncedChatId(activeChatId);
    if (activeChat) setMessages(activeChat.messages);
  }
}

interface DeletedThread {
  chat: Chat;
  index: number;
}

interface ThreadActionsParams {
  chats: Chat[];
  activeChatId: string | null;
  deleted: DeletedThread | null;
  deleteChat: (id: string) => DeletedThread | null;
  restoreChat: (chat: Chat, index: number) => void;
  setActiveChatId: Dispatch<SetStateAction<string | null>>;
  setMessages: Dispatch<SetStateAction<Message[]>>;
  setInput: Dispatch<SetStateAction<string>>;
  setFailure: Dispatch<SetStateAction<string | null>>;
  setDeleted: Dispatch<SetStateAction<DeletedThread | null>>;
}

/** Starting, opening, deleting and restoring threads. */
function useThreadActions(p: ThreadActionsParams) {
  const { chats, activeChatId, deleted, deleteChat, restoreChat } = p;
  const { setActiveChatId, setMessages, setInput, setFailure, setDeleted } = p;

  const handleNewChat = useCallback(() => {
    setActiveChatId(null);
    setMessages([]);
    setInput("");
    setFailure(null);
    setDeleted(null);
  }, [setActiveChatId, setMessages, setInput, setFailure, setDeleted]);

  const handleSelectChat = useCallback(
    (id: string) => {
      const chat = chats.find((c) => c.id === id);
      if (!chat) return;
      setActiveChatId(id);
      setMessages(chat.messages);
      setFailure(null);
    },
    [chats, setActiveChatId, setMessages, setFailure],
  );

  const handleDeleteChat = useCallback(
    (id: string) => {
      const removed = deleteChat(id);
      if (!removed) return;
      setDeleted(removed);
      if (activeChatId === id) {
        setActiveChatId(null);
        setMessages([]);
      }
    },
    [activeChatId, deleteChat, setActiveChatId, setMessages, setDeleted],
  );

  const undoDelete = useCallback(() => {
    if (!deleted) return;
    restoreChat(deleted.chat, deleted.index);
    setDeleted(null);
  }, [deleted, restoreChat, setDeleted]);

  return { handleNewChat, handleSelectChat, handleDeleteChat, undoDelete };
}

interface AnsweringParams {
  activeChatId: string | null;
  messages: Message[];
  input: string;
  isLoading: boolean;
  createChat: () => Chat;
  addMessage: (chatId: string, message: Message) => void;
  storeMessages: (chatId: string, messages: Message[]) => void;
  setActiveChatId: Dispatch<SetStateAction<string | null>>;
  setMessages: Dispatch<SetStateAction<Message[]>>;
  setInput: Dispatch<SetStateAction<string>>;
  setIsLoading: Dispatch<SetStateAction<boolean>>;
  setToolStatus: Dispatch<SetStateAction<string | null>>;
  setFailure: Dispatch<SetStateAction<string | null>>;
  setDeleted: Dispatch<SetStateAction<DeletedThread | null>>;
}

/** Asking the engineer: a question, the same one again, and the one that failed. */
function useAnswering(p: AnsweringParams) {
  const { activeChatId, messages, input, isLoading, createChat, addMessage, storeMessages } = p;
  const { setActiveChatId, setMessages, setInput, setIsLoading, setToolStatus, setFailure, setDeleted } = p;

  /** Asks `text` after `history`, the turns that stay in the thread. */
  const ask = useCallback(
    async (text: string, history: Message[]) => {
      const chatId = activeChatId ?? createChat().id;
      setActiveChatId(chatId);
      const asked: Message[] = [...history, { role: "user", content: text }];
      setMessages(asked);
      // The turns that stay are written back first: a regenerated answer is not kept in the store either.
      storeMessages(chatId, history);
      addMessage(chatId, asked[asked.length - 1]);
      setInput("");
      setFailure(null);
      setDeleted(null);
      setIsLoading(true);
      try {
        const body = await requestAnswer(asked, chatId);
        addMessage(chatId, await readAnswer(body, { setMessages, setToolStatus }));
      } catch (error) {
        setMessages(asked);
        setFailure(error instanceof AnswerFailure ? error.message : UNREACHABLE_REASON);
      } finally {
        setIsLoading(false);
        setToolStatus(null);
      }
    },
    [
      activeChatId,
      createChat,
      addMessage,
      storeMessages,
      setActiveChatId,
      setMessages,
      setInput,
      setFailure,
      setDeleted,
      setIsLoading,
      setToolStatus,
    ],
  );

  const sendMessage = useCallback((text: string) => ask(text, messages), [ask, messages]);

  const handleSubmit = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();
      if (input.trim()) await sendMessage(input.trim());
    },
    [input, sendMessage],
  );

  /** Asks the last question again; the answer it replaces is not kept. */
  const regenerate = useCallback(async () => {
    if (isLoading || messages.length < 2) return;
    const lastUser = messages.map((m) => m.role).lastIndexOf("user");
    await ask(messages[lastUser].content, messages.slice(0, lastUser));
  }, [ask, isLoading, messages]);

  /** After a failure the last turn is the question with no answer: it goes, and is asked again. */
  const retry = useCallback(async () => {
    await ask(messages[messages.length - 1].content, messages.slice(0, -1));
  }, [ask, messages]);

  return { sendMessage, handleSubmit, regenerate, retry };
}

export function useChat() {
  const { chats, createChat, deleteChat, restoreChat, addMessage, setMessages: storeMessages } = useLocalChats();

  const [activeChatId, setActiveChatId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [toolStatus, setToolStatus] = useState<string | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const [deleted, setDeleted] = useState<DeletedThread | null>(null);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const activeChat = chats.find((c) => c.id === activeChatId) ?? null;
  useSyncedThreadMessages(activeChatId, activeChat, setMessages);
  useChatViewEffects(messagesEndRef, inputRef, messages, isLoading);

  const answering = useAnswering({
    activeChatId,
    messages,
    input,
    isLoading,
    createChat,
    addMessage,
    storeMessages,
    setActiveChatId,
    setMessages,
    setInput,
    setIsLoading,
    setToolStatus,
    setFailure,
    setDeleted,
  });

  const threads = useThreadActions({
    chats,
    activeChatId,
    deleted,
    deleteChat,
    restoreChat,
    setActiveChatId,
    setMessages,
    setInput,
    setFailure,
    setDeleted,
  });

  return {
    chats,
    activeChatId,
    activeChat,
    messages,
    input,
    isLoading,
    toolStatus,
    failure,
    deleted,
    messagesEndRef,
    inputRef,
    setInput,
    ...answering,
    ...threads,
  };
}
