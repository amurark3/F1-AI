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
  const [toolStatus, setToolStatus] = useState<string | null>(null);
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
        const chunk = decoder.decode(value, { stream: true });

        // Parse tool status indicators from the stream.
        // Format: [TOOL_START]Tool Name[/TOOL_START] and [TOOL_END]Tool Name[/TOOL_END]
        const remaining = chunk.replace(/\[TOOL_START\](.*?)\[\/TOOL_START\]/g, (_, name) => {
          setToolStatus(name);
          return '';
        }).replace(/\[TOOL_END\](.*?)\[\/TOOL_END\]/g, () => {
          setToolStatus(null);
          return '';
        });

        if (remaining) {
          assistantContent += remaining;
          setMessages((prev) => {
            const updated = [...prev];
            updated[updated.length - 1] = { role: 'assistant', content: assistantContent };
            return updated;
          });
        }
      }

      updateLastMessage(chatId, assistantContent);
    } catch (error) {
      console.error('Chat error:', error);
      const errMsg = `**Connection Error:** Could not reach the backend. Make sure the server is running.\n\n_${error}_`;
      setMessages((prev) => [...prev, { role: 'assistant', content: errMsg }]);
      addMessage(chatId, { role: 'assistant', content: errMsg });
    } finally {
      setIsLoading(false);
      setToolStatus(null);
    }
  }, [activeChatId, messages, createChat, addMessage, updateLastMessage]);

  const handleSubmit = useCallback(async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim()) return;
    await sendMessage(input.trim());
  }, [input, sendMessage]);

  const regenerate = useCallback(async () => {
    if (isLoading || messages.length < 2) return;

    // Find the last user message
    let lastUserMsg: string | null = null;
    for (let i = messages.length - 1; i >= 0; i--) {
      if (messages[i].role === 'user') {
        lastUserMsg = messages[i].content;
        break;
      }
    }
    if (!lastUserMsg) return;

    // Remove the last assistant message from state and local storage
    setMessages((prev) => {
      const trimmed = [...prev];
      // Remove trailing assistant message(s) until we hit the last user message
      while (trimmed.length > 0 && trimmed[trimmed.length - 1].role === 'assistant') {
        trimmed.pop();
      }
      return trimmed;
    });

    // Re-send the last user message (sendMessage adds a new user msg + assistant response)
    // But we need to remove the last user message too since sendMessage will re-add it
    setMessages((prev) => {
      const trimmed = [...prev];
      if (trimmed.length > 0 && trimmed[trimmed.length - 1].role === 'user') {
        trimmed.pop();
      }
      return trimmed;
    });

    await sendMessage(lastUserMsg);
  }, [isLoading, messages, sendMessage]);

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
