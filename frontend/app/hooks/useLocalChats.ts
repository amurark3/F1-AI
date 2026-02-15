import { useState, useCallback, useEffect } from 'react';

export interface Message {
  role: 'user' | 'assistant';
  content: string;
}

export interface Chat {
  id: string;
  title: string;
  updatedAt: number;
  messages: Message[];
}

const STORAGE_KEY = 'f1ai_chats';

function readChats(): Chat[] {
  if (typeof window === 'undefined') return [];
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

function writeChats(chats: Chat[]) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(chats));
}

export function useLocalChats() {
  const [chats, setChats] = useState<Chat[]>([]);

  // Load from localStorage on mount.
  useEffect(() => {
    setChats(readChats());
  }, []);

  const persist = useCallback((next: Chat[]) => {
    setChats(next);
    writeChats(next);
  }, []);

  const createChat = useCallback((): Chat => {
    const chat: Chat = {
      id: crypto.randomUUID(),
      title: 'New Chat',
      updatedAt: Date.now(),
      messages: [],
    };
    const next = [chat, ...readChats()];
    persist(next);
    return chat;
  }, [persist]);

  const deleteChat = useCallback((id: string) => {
    persist(readChats().filter((c) => c.id !== id));
  }, [persist]);

  const updateChat = useCallback((id: string, updater: (c: Chat) => Chat) => {
    const all = readChats();
    const idx = all.findIndex((c) => c.id === id);
    if (idx === -1) return;
    all[idx] = updater(all[idx]);
    all[idx].updatedAt = Date.now();
    // Move updated chat to top.
    const [updated] = all.splice(idx, 1);
    persist([updated, ...all]);
  }, [persist]);

  const addMessage = useCallback((chatId: string, msg: Message) => {
    updateChat(chatId, (c) => ({
      ...c,
      messages: [...c.messages, msg],
      // Auto-title from first user message.
      title: c.title === 'New Chat' && msg.role === 'user'
        ? msg.content.slice(0, 50) + (msg.content.length > 50 ? '...' : '')
        : c.title,
    }));
  }, [updateChat]);

  const updateLastMessage = useCallback((chatId: string, content: string) => {
    const all = readChats();
    const chat = all.find((c) => c.id === chatId);
    if (!chat || chat.messages.length === 0) return;
    chat.messages[chat.messages.length - 1].content = content;
    chat.updatedAt = Date.now();
    writeChats(all);
    setChats([...all]);
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
