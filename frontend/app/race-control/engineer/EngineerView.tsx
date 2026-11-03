"use client";

import { BookOpenCheck, Database, LineChart, PanelLeftOpen, SquarePen } from "lucide-react";

import ChatInput from "@/app/components/ChatInput";
import ChatMessages from "@/app/components/ChatMessages";
import ChatSidebar from "@/app/components/ChatSidebar";
import EngineerAvatar from "@/app/components/EngineerAvatar";
import { F1DisclaimerLine } from "@/app/components/SiteFooter";
import { useChat } from "@/app/hooks/useChat";

import { rcFont } from "../components/RaceControlPrimitives";

import { EngineerEmptyState } from "./EngineerEmptyState";

// What the engineer answers from. Neutral chips: these describe the sources,
// they are not statuses, so they do not compete with the red identity.
const SOURCES = [
  { label: "Race data", icon: Database },
  { label: "FIA rules", icon: BookOpenCheck },
  { label: "Predictions", icon: LineChart },
] as const;

const ICON_BUTTON =
  "inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-md border border-[#1E2633] bg-[#0D111B] text-[#8E96A8] transition-colors hover:border-[#2C3646] hover:text-white";

export function EngineerView() {
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
    // Fills the shell's content area edge to edge (a full-bleed route): the
    // history rail sits flush against the Race Control sidebar as a second
    // column of the same chrome, not as a framed window inside the page.
    <div className="flex min-h-0 w-full flex-1 overflow-hidden bg-[#07090D]">
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
        {/* h-16 matches the history rail's header so their borders form one line. */}
        <header className="flex h-16 shrink-0 items-center border-b border-[#1E2633] px-3 sm:px-5">
          <div className="flex w-full items-center justify-between gap-3">
            <div className="flex min-w-0 items-center gap-3">
              <button
                onClick={() => setSidebarOpen(true)}
                className={`${ICON_BUTTON} lg:hidden`}
                aria-label="Open chat history"
              >
                <PanelLeftOpen className="h-4 w-4" />
              </button>
              <EngineerAvatar size="md" />
              <div className="min-w-0">
                <EngineerStatus isLoading={isLoading} toolStatus={toolStatus} />
                <h1 className="truncate text-lg font-black text-white sm:text-xl" style={rcFont}>
                  {activeChat?.title ?? "New strategy thread"}
                </h1>
              </div>
            </div>

            <div className="flex shrink-0 items-center gap-2">
              <div className="hidden items-center gap-1.5 md:flex">
                {SOURCES.map(({ label, icon: Icon }) => (
                  <span
                    key={label}
                    className="inline-flex items-center gap-1.5 rounded border border-[#1E2633] bg-[#0D111B] px-2 py-1 font-mono text-[10px] font-bold uppercase tracking-[0.16em] text-[#8E96A8]"
                  >
                    <Icon className="h-3 w-3 text-[#596173]" />
                    {label}
                  </span>
                ))}
              </div>
              {hasMessages && (
                <button onClick={handleNewChat} className={ICON_BUTTON} aria-label="New chat" title="New chat">
                  <SquarePen className="h-4 w-4" />
                </button>
              )}
            </div>
          </div>
        </header>

        <div className="min-h-0 flex-1 overflow-y-auto">
          {hasMessages ? (
            <ChatMessages
              messages={messages}
              isLoading={isLoading}
              toolStatus={toolStatus}
              messagesEndRef={messagesEndRef}
              onRegenerate={regenerate}
            />
          ) : (
            <EngineerEmptyState onSendMessage={sendMessage} isLoading={isLoading} />
          )}
        </div>

        <ChatInput
          input={input}
          isLoading={isLoading}
          inputRef={inputRef}
          onInputChange={setInput}
          onSubmit={handleSubmit}
        />
        <F1DisclaimerLine className="mx-auto w-full max-w-4xl px-4 pb-3 text-center sm:px-5" />
      </section>
    </div>
  );
}

/** Eyebrow line: amber while the engineer is working, quiet grey otherwise. */
function statusLabel(isLoading: boolean, toolStatus: string | null): string {
  if (toolStatus) return `Running ${toolStatus}`;
  if (isLoading) return "Working on it";
  return "AI Race Engineer";
}

interface EngineerStatusProps {
  isLoading: boolean;
  toolStatus: string | null;
}

function EngineerStatus({ isLoading, toolStatus }: EngineerStatusProps) {
  const busy = isLoading || toolStatus !== null;
  return (
    <p
      className={`flex items-center gap-1.5 truncate font-mono text-[10px] font-bold uppercase tracking-[0.18em] ${
        busy ? "text-[#F5C542]" : "text-[#7F8797]"
      }`}
      aria-live="polite"
    >
      <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${busy ? "bg-[#F5C542] animate-pulse" : "bg-[#00FF78]"}`} />
      {statusLabel(isLoading, toolStatus)}
    </p>
  );
}
