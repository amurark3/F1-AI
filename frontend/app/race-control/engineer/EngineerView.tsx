"use client";

import { F1DisclaimerLine } from "@/app/ui/shell/SiteFooter";
import { WRAP } from "@/app/ui/shell/wrap";
import { EYEBROW } from "@/app/ui/typography";

import { ChatHistory } from "./ChatHistory";
import { ChatThread } from "./ChatThread";
import { useChat } from "./useChat";

/**
 * The AI Engineer: a history rail and a thread, in the shell's `workspace`
 * layout (it fills the viewport and scrolls inside, so it prints its own
 * disclaimer).
 */
export function EngineerView() {
  const { chats, activeChatId, deleted, handleNewChat, handleSelectChat, handleDeleteChat, undoDelete, ...thread } =
    useChat();

  return (
    <div className={`${WRAP} flex min-h-0 flex-1 flex-col pb-4 pt-8`}>
      <h1 className={EYEBROW}>AI Engineer</h1>
      <div className="mt-2 grid min-h-0 flex-1 grid-rows-[auto_minmax(0,1fr)] overflow-hidden rounded-md border border-rc-line md:grid-cols-[260px_minmax(0,1fr)] md:grid-rows-1">
        <ChatHistory
          chats={chats}
          activeChatId={activeChatId}
          deleted={deleted?.chat ?? null}
          onNewChat={handleNewChat}
          onSelectChat={handleSelectChat}
          onDeleteChat={handleDeleteChat}
          onUndoDelete={undoDelete}
        />
        <ChatThread {...thread} />
      </div>
      <p className="mt-3.5 font-mono text-[10px] font-medium uppercase leading-[1.6] tracking-[0.1em] text-rc-ink-3">
        Answers are built from the same data the screens use, and list the sources they read
      </p>
      <F1DisclaimerLine className="mt-1.5" />
    </div>
  );
}
