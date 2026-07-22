"use client";

import { type RefObject } from 'react';
import { Loader2, Mic, MicOff } from 'lucide-react';
import { motion } from 'framer-motion';
import { useVoice } from '@/app/hooks/useVoice';

interface ChatInputProps {
  input: string;
  isLoading: boolean;
  inputRef: RefObject<HTMLInputElement | null>;
  onInputChange: (value: string) => void;
  onSubmit: (e: React.FormEvent) => void;
}

export default function ChatInput({ input, isLoading, inputRef, onInputChange, onSubmit }: ChatInputProps) {
  const { supported: voiceSupported, listening, startListening, stopListening } = useVoice({
    onTranscript: (text) => onInputChange(input ? `${input} ${text}` : text),
  });

  return (
    <div className="shrink-0 border-t border-[#1E2633] bg-[#0B0D0C] p-3 sm:p-4">
      {/* RADIO channel label */}
      <div className="flex items-center gap-2 max-w-4xl mx-auto mb-2">
        <span
          className="h-[6px] w-[6px] rounded-full animate-glow-pulse"
          style={{ background: '#00FF78' }}
        />
        <span
          className="font-mono text-[9px] font-bold uppercase tracking-[0.2em]"
          style={{ color: '#00FF78' }}
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
          placeholder={listening ? "Listening… speak your question" : "Ask for a race brief, driver delta, regulation call, or strategy explanation…"}
          className="flex-1 min-w-0 rounded-md border border-[#1E2633] bg-[#0D111B] px-4 sm:px-5 py-3 text-sm text-white
            focus:outline-none focus:border-[#00FF78]/40 focus:ring-1 focus:ring-[#00FF78]/30
            placeholder:text-[#6F7789] transition-colors duration-200"
          disabled={isLoading}
          autoFocus
        />

        {voiceSupported && (
          <motion.button
            type="button"
            onClick={() => (listening ? stopListening() : startListening())}
            disabled={isLoading}
            whileHover={{ scale: 1.06 }}
            whileTap={{ scale: 0.93 }}
            aria-label={listening ? "Stop voice input" : "Start voice input"}
            title={listening ? "Stop voice input" : "Speak your question"}
            className={`shrink-0 rounded-md border px-4 py-3 transition-colors duration-200 disabled:opacity-25 disabled:cursor-not-allowed ${
              listening
                ? 'border-[#00FF78]/40 bg-[#00FF78]/15 text-[#00FF78]'
                : 'border-[#1E2633] bg-[#0D111B] text-neutral-300 hover:text-white'
            }`}
          >
            {listening ? <Mic className="w-4 h-4 animate-pulse" /> : <MicOff className="w-4 h-4" />}
          </motion.button>
        )}

        <motion.button
          type="submit"
          disabled={isLoading || !input.trim()}
          whileHover={{ scale: 1.04 }}
          whileTap={{ scale: 0.95 }}
          className="shrink-0 rounded-md bg-[#00FF78] px-5 sm:px-7 py-3 text-[11px] font-black uppercase tracking-widest text-black
            transition-colors duration-200 hover:bg-white disabled:opacity-25 disabled:cursor-not-allowed disabled:hover:bg-[#00FF78]"
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
