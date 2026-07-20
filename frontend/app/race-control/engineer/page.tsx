"use client";

import { Bot, PanelLeftOpen, Plus, Radio, Sparkles } from "lucide-react";
import ChatInput from "@/app/components/ChatInput";
import ChatMessages from "@/app/components/ChatMessages";
import ChatSidebar from "@/app/components/ChatSidebar";
import { useChat } from "@/app/hooks/useChat";
import { StatusPill, rcFont } from "../components/RaceControlPrimitives";

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
    sidebarOpen,
    sidebarCollapsed,
    messagesEndRef,
    inputRef,
    setInput,
    setSidebarOpen,
    setSidebarCollapsed,
    sendMessage,
    handleSubmit,
    handleNewChat,
    handleSelectChat,
    handleDeleteChat,
    regenerate,
  } = useChat();

  const hasMessages = messages.length > 0;

  return (
    <div className="h-[calc(100vh-132px)] min-h-[620px] overflow-hidden rounded-lg border border-white/10 bg-[#090B0A]">
      <div className="flex h-full min-h-0">
        <ChatSidebar
          chats={chats}
          activeChatId={activeChatId}
          isOpen={sidebarOpen}
          collapsed={sidebarCollapsed}
          onSelectChat={handleSelectChat}
          onNewChat={handleNewChat}
          onDeleteChat={handleDeleteChat}
          onClose={() => setSidebarOpen(false)}
          onToggleCollapse={() => setSidebarCollapsed((prev) => !prev)}
        />

        <section className="flex min-w-0 flex-1 flex-col">
          <header className="shrink-0 border-b border-white/10 bg-[#0B0D0C]/95 px-3 py-3 sm:px-5">
            <div className="flex items-center justify-between gap-3">
              <div className="flex min-w-0 items-center gap-3">
                <button
                  onClick={() => setSidebarOpen(true)}
                  className="inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-white/10 bg-white/[0.04] text-neutral-300 hover:text-white lg:hidden"
                  aria-label="Open chat history"
                >
                  <PanelLeftOpen className="h-5 w-5" />
                </button>
                <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-[#00FF78]/25 bg-[#00FF78]/10">
                  <Bot className="h-5 w-5 text-[#00FF78]" />
                </div>
                <div className="min-w-0">
                  <p className="text-[10px] font-black uppercase tracking-[0.18em] text-[#00FF78]" style={rcFont}>
                    {toolStatus ? `Running ${toolStatus}` : "AI Race Engineer"}
                  </p>
                  <h1 className="truncate text-lg font-black uppercase text-white sm:text-xl" style={rcFont}>
                    {activeChat?.title ?? "New Strategy Thread"}
                  </h1>
                </div>
              </div>

              <div className="hidden shrink-0 items-center gap-2 sm:flex">
                <StatusPill>Race data</StatusPill>
                <StatusPill color="#3671C6">FIA rules</StatusPill>
                <StatusPill color="#FF8000">Predictions</StatusPill>
              </div>
            </div>
          </header>

          <div className="min-h-0 flex-1 overflow-y-auto bg-black/10">
            {hasMessages ? (
              <ChatMessages
                messages={messages}
                isLoading={isLoading}
                toolStatus={toolStatus}
                messagesEndRef={messagesEndRef}
                onRegenerate={regenerate}
              />
            ) : (
              <div className="flex min-h-full flex-col items-center justify-center px-4 py-8 text-center sm:px-6">
                <div className="mb-5 flex h-14 w-14 items-center justify-center rounded-lg border border-[#00FF78]/25 bg-[#00FF78]/10">
                  <Radio className="h-7 w-7 text-[#00FF78]" />
                </div>
                <p className="text-xs font-black uppercase tracking-[0.18em] text-neutral-500" style={rcFont}>Engineer Console</p>
                <h2 className="mt-2 max-w-3xl text-3xl font-black uppercase leading-tight text-white sm:text-4xl" style={rcFont}>
                  Ask for a decision-ready race answer
                </h2>
                <p className="mt-3 max-w-2xl text-base leading-relaxed text-neutral-400">
                  Strategy briefs, driver deltas, regulation calls, prediction reads, race results, and live-session context stay in this thread.
                </p>

                <button
                  onClick={handleNewChat}
                  className="mt-6 inline-flex h-11 items-center justify-center gap-2 rounded-lg bg-[#00FF78] px-5 text-sm font-black uppercase tracking-wider text-black transition-colors hover:bg-white"
                >
                  <Plus className="h-4 w-4" />
                  New Chat
                </button>

                <div className="mt-8 grid w-full max-w-5xl gap-3 md:grid-cols-2">
                  {PROMPTS.map((prompt) => (
                    <button
                      key={prompt}
                      onClick={() => void sendMessage(prompt)}
                      disabled={isLoading}
                      className="min-h-20 rounded-lg border border-white/10 bg-white/[0.035] px-4 py-3 text-left text-sm leading-relaxed text-neutral-300 transition-colors hover:border-[#00FF78]/30 hover:text-white disabled:opacity-50"
                    >
                      <Sparkles className="mb-2 h-4 w-4 text-[#00FF78]" />
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
        </section>
      </div>
    </div>
  );
}
