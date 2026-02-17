"use client";

import { type RefObject } from 'react';
import { SendHorizontal, Loader2 } from 'lucide-react';
import { motion } from 'framer-motion';

interface ChatInputProps {
  input: string;
  isLoading: boolean;
  inputRef: RefObject<HTMLInputElement | null>;
  onInputChange: (value: string) => void;
  onSubmit: (e: React.FormEvent) => void;
}

export default function ChatInput({ input, isLoading, inputRef, onInputChange, onSubmit }: ChatInputProps) {
  return (
    <div className="shrink-0 border-t border-white/5 glass-strong p-3 sm:p-4">
      <form onSubmit={onSubmit} className="max-w-4xl mx-auto flex gap-3 sm:gap-4">
        <input
          ref={inputRef}
          type="text"
          value={input}
          onChange={(e) => onInputChange(e.target.value)}
          placeholder="Ask about any driver, race, or regulation..."
          className="flex-1 min-w-0 glass border-white/10 text-white rounded-full px-4 sm:px-6 py-3 sm:py-4 text-sm focus:outline-none focus:ring-2 focus:ring-red-500/40 focus:border-red-500/30 focus:shadow-[0_0_20px_rgba(220,38,38,0.15)] placeholder:text-neutral-500 transition-all duration-300"
          disabled={isLoading}
          autoFocus
        />
        <motion.button
          type="submit"
          disabled={isLoading || !input.trim()}
          whileHover={{ scale: 1.1 }}
          whileTap={{ scale: 0.9 }}
          className="shrink-0 bg-gradient-to-r from-red-600 to-orange-500 hover:from-red-500 hover:to-orange-400 text-white px-4 sm:px-6 py-3 sm:py-4 rounded-full text-sm font-bold uppercase tracking-wider shadow-lg shadow-red-600/25 hover:shadow-red-500/30 disabled:opacity-30 disabled:shadow-none disabled:cursor-not-allowed transition-all duration-300"
        >
          {isLoading ? (
            <Loader2 className="w-4 h-4 sm:w-5 sm:h-5 animate-spin" />
          ) : (
            <SendHorizontal className="w-4 h-4 sm:w-5 sm:h-5" />
          )}
        </motion.button>
      </form>
    </div>
  );
}
