"use client";

import { motion } from "framer-motion";
import { Loader2, Mic, SendHorizontal } from "lucide-react";

import { useVoice } from "@/app/hooks/useVoice";

import type { RefObject } from "react";

interface ChatInputProps {
  input: string;
  isLoading: boolean;
  inputRef: RefObject<HTMLInputElement | null>;
  onInputChange: (value: string) => void;
  onSubmit: (e: React.FormEvent) => void;
}

function inputPlaceholder(listening: boolean): string {
  return listening
    ? "Listening… speak your question"
    : "Ask for a race brief, driver delta, regulation call, or strategy explanation…";
}

export default function ChatInput({ input, isLoading, inputRef, onInputChange, onSubmit }: ChatInputProps) {
  const {
    supported: voiceSupported,
    listening,
    startListening,
    stopListening,
  } = useVoice({
    onTranscript: (text) => onInputChange(input ? `${input} ${text}` : text),
  });

  return (
    // Sits on the page, not in a chrome bar; the fade lets the thread scroll
    // out beneath it instead of ending at a hard rule.
    <div className="relative shrink-0 px-3 pb-2 pt-1 before:pointer-events-none before:absolute before:inset-x-0 before:-top-6 before:h-6 before:bg-gradient-to-t before:from-[#07090D] before:to-transparent sm:px-4">
      <form onSubmit={onSubmit} className="mx-auto max-w-4xl">
        {/* One field: the input and its actions share the focus ring. */}
        <div className="flex items-center gap-1.5 rounded-md border border-[#1E2633] bg-[#0D111B] p-1.5 pl-4 transition-colors duration-200 focus-within:border-[#E10600]/35">
          <input
            ref={inputRef}
            type="text"
            value={input}
            onChange={(e) => onInputChange(e.target.value)}
            placeholder={inputPlaceholder(listening)}
            aria-label="Message the race engineer"
            className="min-w-0 flex-1 bg-transparent py-2 text-sm text-white placeholder:text-[#596173] focus:outline-none"
            disabled={isLoading}
            autoFocus
          />

          {voiceSupported && (
            <motion.button
              type="button"
              onClick={() => (listening ? stopListening() : startListening())}
              disabled={isLoading}
              whileTap={{ scale: 0.93 }}
              aria-label={listening ? "Stop voice input" : "Start voice input"}
              aria-pressed={listening}
              title={listening ? "Stop voice input" : "Speak your question"}
              className={`inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-md transition-colors duration-200 disabled:cursor-not-allowed disabled:opacity-40 ${
                listening ? "bg-[#E10600]/15 text-[#FF4655]" : "text-[#8E96A8] hover:bg-white/[0.05] hover:text-white"
              }`}
            >
              <Mic className={`h-4 w-4 ${listening ? "animate-pulse" : ""}`} />
            </motion.button>
          )}

          <motion.button
            type="submit"
            disabled={isLoading || !input.trim()}
            whileTap={{ scale: 0.95 }}
            aria-label="Send message"
            className="inline-flex h-9 shrink-0 items-center justify-center gap-2 rounded-md bg-[#E10600] px-3 text-[11px] font-black uppercase tracking-widest text-white transition-colors duration-200 hover:bg-[#FF4655] disabled:cursor-not-allowed disabled:bg-[#1E2633] disabled:text-[#596173] sm:px-4"
          >
            {isLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <SendHorizontal className="h-4 w-4" />}
            <span className="hidden sm:inline">Send</span>
          </motion.button>
        </div>

        <ChannelStatus isLoading={isLoading} />
      </form>
    </div>
  );
}

/** Team-radio style status under the field: green while open, amber while transmitting. */
function ChannelStatus({ isLoading }: { isLoading: boolean }) {
  return (
    <div className="mt-2 flex items-center justify-between gap-3 px-1 font-mono text-[9px] font-bold uppercase tracking-[0.2em]">
      <span className={`flex items-center gap-2 ${isLoading ? "text-[#F5C542]" : "text-[#6F7789]"}`}>
        <span
          className={`h-1.5 w-1.5 rounded-full ${isLoading ? "bg-[#F5C542] animate-pulse" : "bg-[#00FF78] animate-glow-pulse"}`}
        />
        {isLoading ? "Engineer transmitting" : "Race engineer channel"}
      </span>
      <span className="hidden text-[#3A4354] sm:inline">Enter to send</span>
    </div>
  );
}
