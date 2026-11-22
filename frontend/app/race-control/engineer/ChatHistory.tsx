"use client";

import { useState } from "react";

import { historyGroups, type Chat, type HistoryEntry } from "./engineerModel";

const GROUP_LABEL =
  "mb-2 mt-[18px] font-mono text-[10px] font-semibold uppercase leading-none tracking-[0.18em] text-rc-ink-3";
const QUIET_BUTTON =
  "font-mono text-[10px] font-medium uppercase tracking-[0.1em] text-rc-ink-2 underline decoration-rc-line underline-offset-[3px] hover:text-rc-ink";

interface ChatHistoryProps {
  chats: Chat[];
  activeChatId: string | null;
  /** The thread just deleted: its row reads as an undo line. */
  deleted: Chat | null;
  onNewChat: () => void;
  onSelectChat: (id: string) => void;
  onDeleteChat: (id: string) => void;
  onUndoDelete: () => void;
}

interface RowProps {
  chat: Chat;
  active: boolean;
  onSelect: () => void;
  onDelete: () => void;
}

function ChatRow({ chat, active, onSelect, onDelete }: RowProps) {
  return (
    <div className="group relative flex items-center rounded">
      <button
        type="button"
        onClick={onSelect}
        aria-current={active ? "true" : undefined}
        className={`block w-full truncate rounded px-2.5 py-[9px] pr-8 text-left text-[13px] ${
          active ? "bg-rc-raised text-rc-ink" : "text-rc-ink-2 hover:text-rc-ink"
        }`}
      >
        {chat.title}
      </button>
      <button
        type="button"
        aria-label={`Delete thread: ${chat.title}`}
        onClick={onDelete}
        className={`absolute right-1 top-1/2 grid size-6 -translate-y-1/2 place-items-center rounded-[3px] font-mono text-[15px] leading-none text-rc-ink-3 hover:bg-white/[0.06] hover:text-rc-ink group-focus-within:opacity-100 group-hover:opacity-100 focus-visible:opacity-100 [@media(hover:none)]:opacity-100 ${
          active ? "opacity-100" : "opacity-0"
        }`}
      >
        ×
      </button>
    </div>
  );
}

function UndoLine({ chat, onUndo }: { chat: Chat; onUndo: () => void }) {
  return (
    <p className="flex items-center gap-2 rounded border border-dashed border-rc-line px-2.5 py-[9px] font-mono text-[10px] font-medium uppercase leading-[1.4] tracking-[0.1em] text-rc-ink-3">
      <span className="min-w-0 flex-1">Deleted · {chat.title}</span>
      <button type="button" onClick={onUndo} className={QUIET_BUTTON}>
        Undo
      </button>
    </p>
  );
}

/** The history rail: "New question", then the threads in "Today" and "Earlier"; one row at a time can read as an undo line. */
export function ChatHistory({
  chats,
  activeChatId,
  deleted,
  onNewChat,
  onSelectChat,
  onDeleteChat,
  onUndoDelete,
}: ChatHistoryProps) {
  // Phones only: the list is closed until History is pressed.
  const [open, setOpen] = useState(false);
  // Read once: "Today" is the day the page was opened.
  const [now] = useState(Date.now);
  const groups = historyGroups(chats, now, deleted);

  const entry = ({ chat, deleted: gone }: HistoryEntry) =>
    gone ? (
      <UndoLine key={chat.id} chat={chat} onUndo={onUndoDelete} />
    ) : (
      <ChatRow
        key={chat.id}
        chat={chat}
        active={chat.id === activeChatId}
        onSelect={() => {
          onSelectChat(chat.id);
          setOpen(false);
        }}
        onDelete={() => onDeleteChat(chat.id)}
      />
    );

  return (
    <aside
      aria-label="Conversations"
      className="border-b border-rc-line bg-rc-hero p-3 md:border-b-0 md:border-r md:p-[18px]"
    >
      <div className="flex gap-2">
        <button
          type="button"
          onClick={onNewChat}
          className="flex h-[38px] min-w-0 flex-1 items-center justify-center bg-f1-red px-6 font-display text-[15px] font-extrabold uppercase leading-none tracking-[0.02em] text-rc-ink transition-colors hover:brightness-110"
        >
          New question
        </button>
        {chats.length > 0 && (
          <button
            type="button"
            aria-expanded={open}
            aria-controls="engineer-history"
            onClick={() => setOpen((value) => !value)}
            className="inline-flex shrink-0 items-center rounded border border-rc-line px-3 font-mono text-[11px] font-semibold uppercase leading-none tracking-[0.14em] text-rc-ink-2 md:hidden"
          >
            History · {chats.length}
          </button>
        )}
      </div>
      <div id="engineer-history" className={open ? "block" : "hidden md:block"}>
        {groups.map((group) => (
          <section key={group.label} aria-label={group.label}>
            <p className={GROUP_LABEL}>{group.label}</p>
            <div className="flex flex-col gap-0.5">{group.entries.map(entry)}</div>
          </section>
        ))}
      </div>
    </aside>
  );
}
