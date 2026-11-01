"use client";

import { motion } from "framer-motion";
import { Loader2, RefreshCw } from "lucide-react";

import ChatMarkdown from "./ChatMarkdown";
import EngineerAvatar from "./EngineerAvatar";

import type { Message } from "../hooks/useLocalChats";
import type { RefObject } from "react";

interface ChatMessagesProps {
  messages: Message[];
  isLoading: boolean;
  toolStatus: string | null;
  messagesEndRef: RefObject<HTMLDivElement | null>;
  onRegenerate?: () => void;
}

const ENTER = { initial: { opacity: 0, y: 8 }, animate: { opacity: 1, y: 0 }, transition: { duration: 0.2 } };

function EngineerLabel() {
  return (
    <p className="mb-1.5 font-mono text-[10px] font-bold uppercase tracking-[0.18em] text-[#7F8797]">Race Engineer</p>
  );
}

function TypingIndicator({ toolStatus }: { toolStatus: string | null }) {
  return (
    <motion.div {...ENTER} className="flex w-full items-start gap-3">
      <EngineerAvatar />
      <div className="min-w-0">
        <EngineerLabel />
        <div className="inline-flex items-center gap-2.5 rounded-md rounded-tl-none border border-[#1E2633] bg-[#0D111B] px-4 py-3 text-sm text-[#8E96A8]">
          <Loader2 className="h-4 w-4 shrink-0 animate-spin text-[#F5C542]" />
          {toolStatus ? (
            <span>
              Running <span className="font-mono font-medium text-[#F5C542]">{toolStatus}</span>
              <span className="animate-pulse">…</span>
            </span>
          ) : (
            <span>
              Analyzing<span className="animate-pulse">…</span>
            </span>
          )}
        </div>
      </div>
    </motion.div>
  );
}

function MessageBubble({ message }: { message: Message }) {
  if (message.role === "user") {
    return (
      <motion.div {...ENTER} className="flex w-full justify-end">
        <div className="max-w-[85%] whitespace-pre-wrap break-words rounded-md rounded-tr-none border border-[#2C3646] bg-[#161D28] px-4 py-3 text-sm leading-relaxed text-white">
          {message.content}
        </div>
      </motion.div>
    );
  }

  return (
    <motion.div {...ENTER} className="flex w-full items-start gap-3">
      <EngineerAvatar />
      <div className="min-w-0 max-w-[calc(100%-2.75rem)]">
        <EngineerLabel />
        <div className="break-words rounded-md rounded-tl-none border border-[#1E2633] bg-[#0D111B] px-4 py-3 text-sm leading-relaxed text-[#C9CED8]">
          <ChatMarkdown content={message.content} />
        </div>
      </div>
    </motion.div>
  );
}

export default function ChatMessages({
  messages,
  isLoading,
  toolStatus,
  messagesEndRef,
  onRegenerate,
}: ChatMessagesProps) {
  const lastMessage = messages[messages.length - 1];
  const showTyping = isLoading && lastMessage?.content === "";
  const showRegenerate =
    !isLoading && messages.length >= 2 && lastMessage?.role === "assistant" && lastMessage?.content !== "";

  return (
    <div className="mx-auto max-w-4xl space-y-6 p-4 md:p-6">
      {messages.map((msg, index) => {
        if (msg.role === "assistant" && msg.content === "" && index === messages.length - 1 && isLoading) {
          return null;
        }
        return <MessageBubble key={index} message={msg} />;
      })}

      {showTyping && <TypingIndicator toolStatus={toolStatus} />}

      {showRegenerate && onRegenerate && (
        <motion.div {...ENTER} className="flex justify-start pl-11">
          <button
            onClick={onRegenerate}
            className="flex items-center gap-2 rounded-md border border-[#1E2633] px-3 py-1.5 text-xs font-medium text-[#6F7789] transition-colors duration-200 hover:border-[#2C3646] hover:bg-white/[0.03] hover:text-white"
          >
            <RefreshCw className="h-3 w-3" />
            Regenerate response
          </button>
        </motion.div>
      )}

      <div ref={messagesEndRef} />
    </div>
  );
}
