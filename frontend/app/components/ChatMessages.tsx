"use client";

import { motion } from "framer-motion";
import { Loader2, RefreshCw } from "lucide-react";

import type { Message } from "../hooks/useLocalChats";
import type { RefObject } from "react";

interface ChatMessagesProps {
  messages: Message[];
  isLoading: boolean;
  toolStatus: string | null;
  messagesEndRef: RefObject<HTMLDivElement | null>;
  onRegenerate?: () => void;
}

function TypingIndicator({ toolStatus }: { toolStatus: string | null }) {
  return (
    <motion.div
      initial={{ opacity: 0, x: -20 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ type: "spring", damping: 20, stiffness: 200 }}
      className="flex w-full justify-start"
    >
      <div className="rounded-lg border border-[#1E2633] bg-[#0D111B] p-4">
        <div className="flex items-center gap-3">
          <Loader2 className="h-5 w-5 text-[#00FF78] animate-spin" />
          <span className="text-sm text-neutral-400">
            {toolStatus ? (
              <>
                Running <span className="font-mono font-medium text-[#00FF78]">{toolStatus}</span>
                <span className="animate-pulse">...</span>
              </>
            ) : (
              <>
                Analyzing<span className="animate-pulse">...</span>
              </>
            )}
          </span>
        </div>
      </div>
    </motion.div>
  );
}

function MessageBubble({ message }: { message: Message }) {
  const isUser = message.role === "user";

  return (
    <motion.div
      initial={{ opacity: 0, x: isUser ? 30 : -30 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ type: "spring", damping: 22, stiffness: 250 }}
      className={`flex w-full ${isUser ? "justify-end" : "justify-start"}`}
    >
      <div
        className={`max-w-[85%] rounded-lg p-4 ${
          isUser ? "bg-[#00FF78] text-black" : "border border-[#1E2633] bg-[#0D111B] text-neutral-200"
        }`}
      >
        <div className="whitespace-pre-wrap font-mono text-sm leading-relaxed">{message.content}</div>
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
    <div className="max-w-4xl mx-auto p-4 md:p-6 space-y-6">
      {messages.map((msg, index) => {
        if (msg.role === "assistant" && msg.content === "" && index === messages.length - 1 && isLoading) {
          return null;
        }
        return <MessageBubble key={index} message={msg} />;
      })}

      {showTyping && <TypingIndicator toolStatus={toolStatus} />}

      {showRegenerate && onRegenerate && (
        <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="flex justify-start">
          <button
            onClick={onRegenerate}
            className="flex items-center gap-2 text-xs font-medium text-neutral-500 hover:text-white px-3 py-1.5 rounded-md border border-[#1E2633] hover:border-[#00FF78]/30 transition-colors duration-200"
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
