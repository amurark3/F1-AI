"use client";

import { Bot, Plus, Trash2 } from "lucide-react";
import ChatInput from "@/app/components/ChatInput";
import ChatMessages from "@/app/components/ChatMessages";
import { useChat } from "@/app/hooks/useChat";
import { InlineNotice, Panel, SectionHeader, StatusPill, WorkspaceSplit, rcFont } from "../components/RaceControlPrimitives";

const PROMPTS = [
  "Build a race-week strategy brief for the next Grand Prix.",
  "Compare Ferrari and McLaren from a constructor strategy perspective.",
  "What regulation constraints matter for parc ferme decisions?",
  "Give me a live-race commentary plan for safety car, pit stop, and undercut events.",
];

export default function EngineerPage() {
  const {
    chats,
    activeChatId,
    activeChat,
    messages,
    input,
    isLoading,
    toolStatus,
    messagesEndRef,
    inputRef,
    setInput,
    sendMessage,
    handleSubmit,
    handleNewChat,
    handleSelectChat,
    handleDeleteChat,
    regenerate,
  } = useChat();

  const hasMessages = messages.length > 0;

  return (
    <div>
      <SectionHeader
        eyebrow="AI Race Engineer"
        title="Engineer Console"
        description="Ask the strategy desk for race briefs, driver deltas, regulation calls, prediction reads, live-session context, and championship implications."
      />

      <Panel className="mb-7 p-5">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <p className="text-xs font-black uppercase tracking-[0.16em] text-neutral-400" style={rcFont}>Available Context</p>
            <h2 className="mt-1 text-2xl font-black text-white" style={rcFont}>Race data, regulations, predictions, and live context</h2>
          </div>
          <div className="flex flex-wrap gap-2">
            <StatusPill>Race context</StatusPill>
            <StatusPill color="#3671C6">FIA citations</StatusPill>
            <StatusPill color="#FF8000">Prediction read</StatusPill>
          </div>
        </div>
      </Panel>

      <WorkspaceSplit className="xl:[&>*:first-child]:basis-[300px] xl:[&>*:first-child]:shrink-0 xl:[&>*:last-child]:flex-1">
        <Panel className="p-4 xl:min-h-[650px]">
          <div className="flex items-center justify-between gap-3 mb-4">
            <div>
              <p className="text-xs font-black uppercase tracking-[0.18em] text-neutral-400" style={rcFont}>Conversations</p>
              <p className="text-sm text-neutral-500">Local web history only</p>
            </div>
            <button
              onClick={handleNewChat}
              className="inline-flex h-10 w-10 items-center justify-center rounded-lg border border-white/10 bg-white/[0.04] text-neutral-300 hover:text-white"
              aria-label="Start a new engineer chat"
            >
              <Plus className="h-4 w-4" />
            </button>
          </div>

          {chats.length === 0 ? (
            <InlineNotice title="No Chats Yet">
              Start with a race brief, regulation call, prediction request, or driver comparison.
            </InlineNotice>
          ) : (
            <div className="space-y-2">
              {chats.map((chat) => {
                const active = chat.id === activeChatId;
                return (
                  <div
                    key={chat.id}
                    className={`group flex items-center gap-2 rounded-lg border px-3 py-2 transition-colors ${
                      active ? "border-[#00FF78]/35 bg-[#00FF78]/10" : "border-white/10 bg-white/[0.03] hover:bg-white/[0.05]"
                    }`}
                  >
                    <button onClick={() => handleSelectChat(chat.id)} className="min-w-0 flex-1 text-left">
                      <p className="truncate text-sm font-bold text-white">{chat.title}</p>
                      <p className="text-xs text-neutral-500">{chat.messages.length} messages</p>
                    </button>
                    <button
                      onClick={() => handleDeleteChat(chat.id)}
                      className="opacity-70 transition-opacity hover:opacity-100"
                      aria-label={`Delete ${chat.title}`}
                    >
                      <Trash2 className="h-4 w-4 text-neutral-500 hover:text-[#E10600]" />
                    </button>
                  </div>
                );
              })}
            </div>
          )}
        </Panel>

        <Panel className="flex h-[calc(100vh-230px)] min-h-[650px] flex-col overflow-hidden">
          <div className="border-b border-white/10 px-5 py-4">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <div className="min-w-0">
                <p className="text-xs font-black uppercase tracking-[0.18em] text-[#00FF78]" style={rcFont}>
                  {toolStatus ? `Running ${toolStatus}` : "Engineer Channel"}
                </p>
                <h2 className="truncate text-2xl font-black italic uppercase text-white" style={rcFont}>
                  {activeChat?.title ?? "New Strategy Thread"}
                </h2>
              </div>
              <Bot className="h-6 w-6 text-[#00FF78]" />
            </div>
          </div>

          <div className="flex-1 overflow-y-auto bg-black/10">
            {hasMessages ? (
              <ChatMessages
                messages={messages}
                isLoading={isLoading}
                toolStatus={toolStatus}
                messagesEndRef={messagesEndRef}
                onRegenerate={regenerate}
              />
            ) : (
              <div className="flex min-h-full flex-col items-center justify-center px-5 py-10 text-center">
                <div className="mb-5 flex h-14 w-14 items-center justify-center rounded-lg border border-[#00FF78]/25 bg-[#00FF78]/10">
                  <Bot className="h-7 w-7 text-[#00FF78]" />
                </div>
                <h2 className="text-3xl font-black italic uppercase text-white" style={rcFont}>Ask The Race Engineer</h2>
                <p className="mt-2 max-w-2xl text-base leading-relaxed text-neutral-400">
                  Ask for strategy briefs, driver deltas, regulation calls, predictions, race results, or live-session context.
                </p>
                <div className="mt-8 flex w-full max-w-4xl flex-col gap-3 md:flex-row md:flex-wrap [&>button]:min-w-[260px] [&>button]:flex-1">
                  {PROMPTS.map((prompt) => (
                    <button
                      key={prompt}
                      onClick={() => void sendMessage(prompt)}
                      disabled={isLoading}
                      className="rounded-lg border border-white/10 bg-white/[0.035] px-4 py-3 text-left text-sm text-neutral-300 transition-colors hover:border-[#00FF78]/30 hover:text-white disabled:opacity-50"
                    >
                      {prompt}
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>

          <ChatInput
            input={input}
            isLoading={isLoading}
            inputRef={inputRef}
            onInputChange={setInput}
            onSubmit={handleSubmit}
          />
        </Panel>
      </WorkspaceSplit>
    </div>
  );
}
