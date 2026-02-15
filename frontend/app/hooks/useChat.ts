"use client";

import { useState, useRef, useEffect, useCallback } from 'react';
import { useLocalChats, type Message } from './useLocalChats';
import { API_BASE } from '../constants/api';

export function useChat() {
  const { chats, createChat, deleteChat, addMessage, updateLastMessage } = useLocalChats();

  const [activeChatId, setActiveChatId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const activeChat = chats.find((c) => c.id === activeChatId) ?? null;

  // Sync messages when switching chats.
  useEffect(() => {
    if (activeChat) {
      setMessages(activeChat.messages);
    }
  }, [activeChatId]); // eslint-disable-line react-hooks/exhaustive-deps

  // Auto-scroll on new messages.
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // Re-focus input after response completes.
  useEffect(() => {
    if (!isLoading) inputRef.current?.focus();
  }, [isLoading]);

  const handleNewChat = useCallback(() => {
    setActiveChatId(null);
    setMessages([]);
    setInput('');
    setSidebarOpen(false);
  }, []);

  const handleSelectChat = useCallback((id: string) => {
    const chat = chats.find((c) => c.id === id);
    if (chat) {
      setActiveChatId(id);
      setMessages(chat.messages);
    }
  }, [chats]);

  const handleDeleteChat = useCallback((id: string) => {
    deleteChat(id);
    if (activeChatId === id) {
      setActiveChatId(null);
      setMessages([]);
    }
  }, [activeChatId, deleteChat]);

  const sendMessage = useCallback(async (text: string) => {
    let chatId = activeChatId;
    if (!chatId) {
      const chat = createChat();
      chatId = chat.id;
      setActiveChatId(chatId);
    }

    const userMessage: Message = { role: 'user', content: text };
    setMessages((prev) => [...prev, userMessage]);
    addMessage(chatId, userMessage);
    setInput('');
    setIsLoading(true);

    try {
      const response = await fetch(`${API_BASE}/api/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ messages: [...messages, userMessage] }),
      });

      if (!response.ok) throw new Error(`Server error: ${response.status}`);
      if (!response.body) throw new Error('No response stream received.');

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let assistantContent = '';

      const emptyAssistant: Message = { role: 'assistant', content: '' };
      setMessages((prev) => [...prev, emptyAssistant]);
      addMessage(chatId, emptyAssistant);

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        assistantContent += decoder.decode(value, { stream: true });
        setMessages((prev) => {
          const updated = [...prev];
          updated[updated.length - 1] = { role: 'assistant', content: assistantContent };
          return updated;
        });
      }

      updateLastMessage(chatId, assistantContent);
    } catch (error) {
      console.error('Chat error:', error);
      const errMsg = `**Connection Error:** Could not reach the backend. Make sure the server is running.\n\n_${error}_`;
      setMessages((prev) => [...prev, { role: 'assistant', content: errMsg }]);
      addMessage(chatId, { role: 'assistant', content: errMsg });
    } finally {
      setIsLoading(false);
    }
  }, [activeChatId, messages, createChat, addMessage, updateLastMessage]);

  const handleSubmit = useCallback(async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim()) return;
    await sendMessage(input.trim());
  }, [input, sendMessage]);

  return {
    // State
    chats,
    activeChatId,
    activeChat,
    messages,
    input,
    isLoading,
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
  };
}
