"use client";

import { MAX_QUESTION_CHARS } from "./engineerModel";

import type { FormEvent, RefObject } from "react";

interface ChatInputProps {
  input: string;
  isLoading: boolean;
  inputRef: RefObject<HTMLInputElement | null>;
  onInputChange: (value: string) => void;
  onSubmit: (e: FormEvent) => void;
}

/** The question field at the foot of the thread; the `⏎` tag sends. */
export function ChatInput({ input, isLoading, inputRef, onInputChange, onSubmit }: ChatInputProps) {
  return (
    <form
      onSubmit={onSubmit}
      className="flex items-center gap-2.5 rounded-lg border border-rc-line bg-(--surface) px-3.5 py-3"
    >
      <input
        ref={inputRef}
        type="text"
        value={input}
        maxLength={MAX_QUESTION_CHARS}
        onChange={(e) => onInputChange(e.target.value)}
        aria-label="Ask the AI Engineer"
        placeholder="Ask about any race, driver, rule or prediction…"
        className="min-w-0 flex-1 bg-transparent text-sm text-rc-ink placeholder:text-rc-ink-3"
        disabled={isLoading}
      />
      <button
        type="submit"
        aria-label="Send"
        disabled={isLoading || !input.trim()}
        className="ml-auto shrink-0 rounded-[2px] bg-white/[0.08] px-[5px] py-[3px] font-mono text-[9px] font-semibold leading-none tracking-[0.14em] text-rc-ink-2 disabled:opacity-50"
      >
        ⏎
      </button>
    </form>
  );
}
