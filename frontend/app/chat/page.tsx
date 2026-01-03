'use client';

import { useState, useRef, useEffect } from 'react';
import Link from 'next/link';

interface Message {
  role: 'user' | 'assistant';
  content: string;
}

export default function ChatInterface() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim()) return;

    const userMessage: Message = { role: 'user', content: input };
    setMessages((prev) => [...prev, userMessage]);
    setInput('');
    setIsLoading(true);

    try {
      const response = await fetch('http://localhost:8000/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ messages: [...messages, userMessage] }),
      });

      if (!response.body) return;
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let assistantMessage = '';

      setMessages((prev) => [...prev, { role: 'assistant', content: '' }]);

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        assistantMessage += decoder.decode(value);
        setMessages((prev) => {
          const newMessages = [...prev];
          newMessages[newMessages.length - 1] = { role: 'assistant', content: assistantMessage };
          return newMessages;
        });
      }
    } catch (error) {
      console.error(error);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <main className="flex flex-col h-screen bg-neutral-950 text-gray-100 font-sans">
      {/* HEADER */}
      <header className="flex items-center justify-between p-4 border-b border-red-900/30 bg-black/40 backdrop-blur">
        <Link href="/" className="text-xl font-bold text-red-500 uppercase cursor-pointer">
          &larr; Exit Pitlane
        </Link>
      </header>

      {/* CHAT AREA */}
      <div className="flex-1 overflow-y-auto p-4 md:p-6 space-y-6">
        {messages.map((msg, index) => (
          <div key={index} className={`flex w-full ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            <div className={`max-w-[85%] rounded-2xl p-4 shadow-lg ${
                msg.role === 'user' ? 'bg-red-900 text-white' : 'bg-gray-900 border border-gray-800'
              }`}>
              {/* This simple tag handles Markdown tables perfectly */}
              <div className="whitespace-pre-wrap font-mono text-sm leading-relaxed">
                {msg.content}
              </div>
            </div>
          </div>
        ))}
        <div ref={messagesEndRef} />
      </div>

      {/* INPUT AREA */}
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
          <button type="submit" disabled={isLoading} className="absolute right-2 top-2 bottom-2 bg-red-600 text-white px-6 rounded-full font-bold">
            {isLoading ? '...' : 'Send'}
          </button>
        </form>
      </div>
    </main>
  );
}