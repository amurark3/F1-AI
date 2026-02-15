"use client";

import { type RefObject } from 'react';
import { type Message } from '../hooks/useLocalChats';

interface ChatMessagesProps {
  messages: Message[];
  isLoading: boolean;
  messagesEndRef: RefObject<HTMLDivElement | null>;
}

function TypingIndicator() {
  return (
    <div className="flex w-full justify-start">
      <div className="rounded-2xl p-4 bg-neutral-900 border border-neutral-800">
        <div className="flex items-center gap-3">
          <div className="relative h-6 w-6">
            <div className="absolute inset-0 rounded-full border-2 border-red-500/20" />
            <div className="absolute inset-0 rounded-full border-2 border-transparent border-t-red-500 animate-spin" />
          </div>
          <span className="text-sm text-gray-400">
            Analyzing<span className="animate-pulse">...</span>
          </span>
        </div>
      </div>
    </div>
  );
}

function MessageBubble({ message }: { message: Message }) {
  const isUser = message.role === 'user';

  return (
    <div className={`flex w-full ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div
        className={`max-w-[85%] rounded-2xl p-4 shadow-lg ${
          isUser
            ? 'bg-red-600 text-white'
            : 'bg-neutral-900 border border-neutral-800'
        }`}
      >
        <div className="whitespace-pre-wrap font-mono text-sm leading-relaxed">
          {message.content}
        </div>
      </div>
    </div>
  );
}

export default function ChatMessages({ messages, isLoading, messagesEndRef }: ChatMessagesProps) {
  const lastMessage = messages[messages.length - 1];
  const showTyping = isLoading && lastMessage?.content === '';

  return (
    <div className="max-w-4xl mx-auto p-4 md:p-6 space-y-5">
      {messages.map((msg, index) => {
        // Hide the empty placeholder while typing indicator is shown.
        if (msg.role === 'assistant' && msg.content === '' && index === messages.length - 1 && isLoading) {
          return null;
        }
        return <MessageBubble key={index} message={msg} />;
      })}

      {showTyping && <TypingIndicator />}

      <div ref={messagesEndRef} />
    </div>
  );
}
