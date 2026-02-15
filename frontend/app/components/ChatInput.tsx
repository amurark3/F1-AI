"use client";

import { type RefObject } from 'react';

interface ChatInputProps {
  input: string;
  isLoading: boolean;
  inputRef: RefObject<HTMLInputElement | null>;
  onInputChange: (value: string) => void;
  onSubmit: (e: React.FormEvent) => void;
}

export default function ChatInput({ input, isLoading, inputRef, onInputChange, onSubmit }: ChatInputProps) {
  return (
    <div className="shrink-0 border-t border-neutral-800/60 bg-neutral-950/90 backdrop-blur-md p-3 sm:p-4">
      <form onSubmit={onSubmit} className="max-w-4xl mx-auto flex gap-2 sm:gap-3">
        <input
          ref={inputRef}
          type="text"
          value={input}
          onChange={(e) => onInputChange(e.target.value)}
          placeholder="Ask about any driver, race, or regulation..."
          className="flex-1 min-w-0 bg-neutral-900 border border-neutral-800 text-white rounded-full px-4 sm:px-6 py-3 sm:py-4 text-sm focus:outline-none focus:ring-2 focus:ring-red-600/60 focus:border-red-600/40 placeholder:text-neutral-600 transition-all"
          disabled={isLoading}
          autoFocus
        />
        <button
          type="submit"
          disabled={isLoading || !input.trim()}
          className="shrink-0 bg-red-600 hover:bg-red-500 text-white px-4 sm:px-6 py-3 sm:py-4 rounded-full text-sm font-bold uppercase tracking-wider disabled:opacity-40 disabled:cursor-not-allowed transition-all"
        >
          {isLoading ? (
            <svg className="animate-spin h-4 w-4 sm:h-5 sm:w-5" viewBox="0 0 24 24" fill="none">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
          ) : 'Send'}
        </button>
      </form>
    </div>
  );
}
