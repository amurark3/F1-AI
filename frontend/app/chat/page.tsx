/**
 * Chat Page — AI Pit Wall
 * =======================
 * Full-screen streaming chat interface for the F1 AI Race Engineer.
 *
 * How it works:
 *  1. User submits a question via the input form.
 *  2. The full message history is POSTed to the backend `/api/chat` endpoint.
 *  3. The response is a plain-text stream (text/plain); chunks are read
 *     incrementally via the Streams API and appended to the last message.
 *  4. The chat list auto-scrolls to the newest message after every update.
 *
 * The backend handles the agentic LLM loop; this component only streams
 * and renders the final text output.
 */
'use client';

import { useState, useRef, useEffect } from 'react';
import Link from 'next/link';
import { API_BASE } from '../constants/api';

interface Message {
  role: 'user' | 'assistant';
  content: string;
}

export default function ChatInterface() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  // Ref attached to a sentinel div at the bottom of the chat list for auto-scroll.
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Scroll to the bottom whenever the message list changes.
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim()) return;

    const userMessage: Message = { role: 'user', content: input };
    // Optimistically add the user message and clear the input immediately.
    setMessages((prev) => [...prev, userMessage]);
    setInput('');
    setIsLoading(true);

    try {
      const response = await fetch(`${API_BASE}/api/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        // Send the full history so the backend has context for follow-up questions.
        body: JSON.stringify({ messages: [...messages, userMessage] }),
      });

      if (!response.ok) {
        throw new Error(`Server error: ${response.status} ${response.statusText}`);
      }

      if (!response.body) {
        throw new Error('No response stream received from server.');
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let assistantMessage = '';

      // Add an empty placeholder message that gets filled as chunks arrive.
      setMessages((prev) => [...prev, { role: 'assistant', content: '' }]);

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        assistantMessage += decoder.decode(value, { stream: true });
        // Update the last message in-place on every chunk for live streaming effect.
        setMessages((prev) => {
          const updated = [...prev];
          updated[updated.length - 1] = { role: 'assistant', content: assistantMessage };
          return updated;
        });
      }
    } catch (error) {
      console.error('Chat error:', error);
      // Surface the error in the chat so the user knows something went wrong.
      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          content: `**Connection Error:** Could not reach the backend. Make sure the server is running on port 8000.\n\n_${error}_`,
        },
      ]);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <main className="flex flex-col h-screen bg-neutral-950 text-gray-100 font-sans">
      {/* Header */}
      <header className="flex items-center justify-between p-4 border-b border-red-900/30 bg-black/40 backdrop-blur">
        <Link href="/" className="text-xl font-bold text-red-500 uppercase cursor-pointer">
          &larr; Exit Pitlane
        </Link>
      </header>

      {/* Message list */}
      <div className="flex-1 overflow-y-auto p-4 md:p-6 space-y-6">
        {messages.map((msg, index) => {
          // Hide the empty assistant placeholder — the loader below replaces it visually.
          if (msg.role === 'assistant' && msg.content === '' && index === messages.length - 1 && isLoading) return null;
          return (
            <div key={index} className={`flex w-full ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
              <div className={`max-w-[85%] rounded-2xl p-4 shadow-lg ${
                  msg.role === 'user' ? 'bg-red-900 text-white' : 'bg-gray-900 border border-gray-800'
                }`}>
                {/* whitespace-pre-wrap preserves Markdown table alignment */}
                <div className="whitespace-pre-wrap font-mono text-sm leading-relaxed">
                  {msg.content}
                </div>
              </div>
            </div>
          );
        })}

        {/* Loading indicator — visible while waiting for stream to begin */}
        {isLoading && messages[messages.length - 1]?.role === 'assistant' && messages[messages.length - 1]?.content === '' && (
          <div className="flex w-full justify-start">
            <div className="max-w-[85%] rounded-2xl p-4 shadow-lg bg-gray-900 border border-gray-800">
              <div className="flex items-center gap-3">
                {/* Spinning wheel — F1 tyre inspired */}
                <div className="relative h-8 w-8">
                  <div className="absolute inset-0 rounded-full border-2 border-red-500/20" />
                  <div className="absolute inset-0 rounded-full border-2 border-transparent border-t-red-500 animate-spin" />
                  <div className="absolute inset-[6px] rounded-full bg-gray-800 border border-gray-700" />
                </div>
                <div className="flex flex-col gap-1">
                  <span className="text-sm font-semibold text-red-400 tracking-wide">
                    Analyzing telemetry
                    <span className="inline-flex w-6">
                      <span className="animate-pulse">...</span>
                    </span>
                  </span>
                  <span className="text-xs text-gray-500">Race Engineer is processing your query</span>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Sentinel element — scrolled into view after every message update */}
        <div ref={messagesEndRef} />
      </div>

      {/* Input area */}
      <div className="p-4 bg-black/80 border-t border-gray-800">
        <form onSubmit={handleSubmit} className="max-w-4xl mx-auto relative flex gap-3">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Compare Norris and Verstappen..."
            className="w-full bg-gray-900 border border-gray-700 text-white rounded-full px-6 py-4 focus:outline-none focus:ring-2 focus:ring-red-600"
            disabled={isLoading}
          />
          <button
            type="submit"
            disabled={isLoading}
            className="absolute right-2 top-2 bottom-2 bg-red-600 text-white px-6 rounded-full font-bold disabled:opacity-60 disabled:cursor-not-allowed transition-opacity"
          >
            {isLoading ? (
              <span className="flex items-center gap-2">
                <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24" fill="none">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
                Live
              </span>
            ) : 'Send'}
          </button>
        </form>
      </div>
    </main>
  );
}
