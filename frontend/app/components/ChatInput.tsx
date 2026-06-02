"use client";

import { type RefObject } from 'react';
import { Loader2 } from 'lucide-react';
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
    <div className="shrink-0 border-t border-white/5 carbon-fiber glass-strong p-3 sm:p-4">
      {/* RADIO channel label */}
      <div className="flex items-center gap-2 max-w-4xl mx-auto mb-2">
        <span
          className="h-[6px] w-[6px] rounded-full animate-glow-pulse"
          style={{ background: '#E10600' }}
        />
        <span
          className="text-[9px] font-black uppercase tracking-[0.2em]"
          style={{ color: '#E10600', fontFamily: 'var(--font-barlow, var(--font-geist-sans))' }}
        >
          Race Engineer Channel
        </span>
      </div>

      <form onSubmit={onSubmit} className="max-w-4xl mx-auto flex gap-2 sm:gap-3">
        <input
          ref={inputRef}
          type="text"
          value={input}
          onChange={(e) => onInputChange(e.target.value)}
          placeholder="Ask for a race brief, driver delta, regulation call, or strategy explanation…"
          className="flex-1 min-w-0 glass rounded-xl px-4 sm:px-5 py-3 text-sm text-white
            focus:outline-none focus:ring-1 focus:ring-[#E10600]/50
            focus:border-[#E10600]/30 focus:shadow-[0_0_16px_rgba(225,6,0,0.12)]
            placeholder:text-neutral-600 transition-all duration-200"
          disabled={isLoading}
          autoFocus
        />

        <motion.button
          type="submit"
          disabled={isLoading || !input.trim()}
          whileHover={{ scale: 1.06 }}
          whileTap={{ scale: 0.93 }}
          className="shrink-0 px-5 sm:px-7 py-3 rounded-xl text-white text-[11px] font-black uppercase tracking-widest
            shadow-lg disabled:opacity-25 disabled:cursor-not-allowed transition-all duration-200"
          style={{
            background: 'linear-gradient(135deg, #E10600 0%, #FF3300 100%)',
            boxShadow: isLoading || !input.trim() ? 'none' : '0 4px 20px rgba(225,6,0,0.35)',
            fontFamily: 'var(--font-barlow, var(--font-geist-sans))',
          }}
        >
          {isLoading ? (
            <Loader2 className="w-4 h-4 animate-spin" />
          ) : (
            'Send'
          )}
        </motion.button>
      </form>
    </div>
  );
}
