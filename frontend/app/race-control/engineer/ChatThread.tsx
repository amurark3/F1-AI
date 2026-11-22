"use client";

import { SectionSkeleton, Section } from "@/app/ui/section/Section";

import { ChatInput } from "./ChatInput";
import { AnswerHeader, EngineerAnswer } from "./EngineerAnswer";
import { StarterPrompts } from "./StarterPrompts";

import type { useChat } from "./useChat";

type Chat = ReturnType<typeof useChat>;

type ChatThreadProps = Pick<
  Chat,
  | "messages"
  | "input"
  | "isLoading"
  | "toolStatus"
  | "failure"
  | "messagesEndRef"
  | "inputRef"
  | "setInput"
  | "sendMessage"
  | "handleSubmit"
  | "regenerate"
  | "retry"
>;

/** "Running Get Driver Standings" while a tool is out, else "Working on it". */
function pendingText(toolStatus: string | null): string {
  return `Engineer · ${toolStatus ? `Running ${toolStatus}` : "Working on it"}`;
}

/** The questions and answers, the starter prompts on an empty thread, and the input at the foot. */
export function ChatThread({
  messages,
  input,
  isLoading,
  toolStatus,
  failure,
  messagesEndRef,
  inputRef,
  setInput,
  sendMessage,
  handleSubmit,
  regenerate,
  retry,
}: ChatThreadProps) {
  const last = messages[messages.length - 1];
  const awaiting = isLoading && (last === undefined || last.role === "user" || last.content === "");
  const latest = messages.length - 1;

  return (
    <div className="flex min-h-0 flex-col bg-(--background)">
      <div
        role="log"
        aria-label="Conversation"
        className="flex min-h-0 flex-1 flex-col gap-[22px] overflow-y-auto p-4 md:px-9 md:py-7"
      >
        {messages.map((message, index) =>
          message.role === "user" ? (
            <p
              key={index}
              className="max-w-[85%] self-end whitespace-pre-wrap break-words rounded-lg bg-rc-raised px-4 py-3 text-rc-ink motion-safe:animate-fade-up md:max-w-[70%]"
            >
              {message.content}
            </p>
          ) : (
            message.content !== "" && (
              <EngineerAnswer
                key={index}
                message={message}
                onRegenerate={index === latest && !isLoading ? () => void regenerate() : undefined}
              />
            )
          ),
        )}
        {awaiting && (
          <div className="max-w-[86%]">
            <AnswerHeader text={pendingText(toolStatus)} live />
            <SectionSkeleton className="h-20" />
          </div>
        )}
        {failure !== null && (
          <div className="max-w-[86%]">
            <Section
              state={{ status: "failed", reason: failure, refreshing: isLoading, retry: () => void retry() }}
              label="Answer"
            >
              <></>
            </Section>
          </div>
        )}
        {messages.length === 0 && !isLoading && (
          <StarterPrompts isLoading={isLoading} onAsk={(text) => void sendMessage(text)} />
        )}
        <div ref={messagesEndRef} />
      </div>
      <div className="px-4 pb-4 md:px-9 md:pb-7">
        <ChatInput
          input={input}
          isLoading={isLoading}
          inputRef={inputRef}
          onInputChange={setInput}
          onSubmit={handleSubmit}
        />
      </div>
    </div>
  );
}
