"use client";

import { motion, AnimatePresence } from "framer-motion";
import { MessageSquare, Plus, Trash2, PanelLeftClose, PanelLeftOpen } from "lucide-react";

import type { Chat } from "../hooks/useLocalChats";

interface ChatSidebarProps {
  chats: Chat[];
  activeChatId: string | null;
  isOpen: boolean;
  collapsed: boolean;
  onSelectChat: (id: string) => void;
  onNewChat: () => void;
  onDeleteChat: (id: string) => void;
  onClose: () => void;
  onToggleCollapse: () => void;
}

// Mirrors the Race Control sidebar's AI Engineer link: a red-tinted tile, not a
// solid fill, so the primary action reads as part of the shell.
const NEW_CHAT_BUTTON =
  "w-full flex items-center justify-center rounded-md border border-[#E10600]/30 bg-[#E10600]/10 text-white hover:border-[#E10600]/50 hover:bg-[#E10600]/20 transition-colors duration-200";

export default function ChatSidebar({
  chats,
  activeChatId,
  isOpen,
  collapsed,
  onSelectChat,
  onNewChat,
  onDeleteChat,
  onClose,
  onToggleCollapse,
}: ChatSidebarProps) {
  return (
    <>
      {/* Mobile overlay */}
      <AnimatePresence>
        {isOpen && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.15 }}
            className="fixed inset-0 bg-black/60 backdrop-blur-sm z-40 lg:hidden"
            onClick={onClose}
          />
        )}
      </AnimatePresence>

      {/* Sidebar */}
      <aside
        className={`
          fixed lg:relative top-0 left-0 z-50 lg:z-auto
          h-full shrink-0
          bg-[#080B11] border-r border-[#1E2633]
          flex flex-col
          transition-all duration-200 ease-out
          ${isOpen ? "translate-x-0" : "-translate-x-full lg:translate-x-0"}
          ${collapsed ? "lg:w-[52px]" : "w-72 lg:w-64"}
        `}
      >
        {/* Header — New Chat button. h-16 matches the chat header so their borders line up. */}
        <div className="flex h-16 shrink-0 items-center px-2 border-b border-[#1E2633]">
          {collapsed ? (
            <button onClick={onNewChat} className={`${NEW_CHAT_BUTTON} p-2`} title="New Chat" aria-label="New Chat">
              <Plus className="w-4 h-4 text-[#FF4655]" />
            </button>
          ) : (
            <button
              onClick={onNewChat}
              className={`${NEW_CHAT_BUTTON} gap-2 px-4 py-2.5 text-[13px] font-bold uppercase tracking-wider`}
            >
              <Plus className="w-4 h-4 text-[#FF4655]" />
              New Chat
            </button>
          )}
        </div>

        {/* Chat list */}
        <div className="flex-1 overflow-y-auto py-2">
          {!collapsed && chats.length > 0 && (
            <p className="px-4 pb-2 pt-1 font-mono text-[10px] font-bold uppercase tracking-[0.2em] text-[#596173]">
              Recent threads
            </p>
          )}
          {chats.length === 0
            ? !collapsed && <p className="text-center text-[#596173] text-xs py-8 px-4">No conversations yet</p>
            : chats.map((chat) => (
                <ChatListItem
                  key={chat.id}
                  chat={chat}
                  isActive={activeChatId === chat.id}
                  collapsed={collapsed}
                  onSelectChat={onSelectChat}
                  onDeleteChat={onDeleteChat}
                  onClose={onClose}
                />
              ))}
        </div>

        {/* Footer — Collapse toggle (desktop only) */}
        <div className="hidden lg:block border-t border-[#1E2633] p-2">
          <button
            onClick={onToggleCollapse}
            className={`
              w-full flex items-center gap-2 p-2 rounded-md
              text-[#6F7789] hover:text-white hover:bg-white/[0.04]
              transition-colors duration-200 text-xs
              ${collapsed ? "justify-center" : "justify-between"}
            `}
            title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          >
            {!collapsed && <span className="font-medium">Collapse</span>}
            {collapsed ? <PanelLeftOpen className="w-4 h-4" /> : <PanelLeftClose className="w-4 h-4" />}
          </button>
        </div>
      </aside>
    </>
  );
}

interface ChatListItemProps {
  chat: Chat;
  isActive: boolean;
  collapsed: boolean;
  onSelectChat: (id: string) => void;
  onDeleteChat: (id: string) => void;
  onClose: () => void;
}

function ChatListItem({ chat, isActive, collapsed, onSelectChat, onDeleteChat, onClose }: ChatListItemProps) {
  return (
    <div
      className={`
        group relative mx-2 mb-1 rounded-md border transition-colors duration-200
        ${
          isActive
            ? "border-[#1E2633] bg-[#121825] text-white"
            : "border-transparent text-[#8E96A8] hover:bg-white/[0.03] hover:text-white"
        }
      `}
    >
      {isActive && <span aria-hidden="true" className="absolute inset-y-2 left-0 w-[2px] rounded-full bg-[#E10600]" />}
      <button
        type="button"
        onClick={() => {
          onSelectChat(chat.id);
          onClose();
        }}
        title={collapsed ? chat.title : undefined}
        aria-current={isActive ? "true" : undefined}
        className={`w-full cursor-pointer flex items-center ${
          collapsed ? "justify-center p-2" : "px-3 py-2.5 pr-9 text-left"
        }`}
      >
        <MessageSquare
          className={`w-4 h-4 shrink-0 ${collapsed ? "" : "mr-2.5"} ${isActive ? "text-[#FF4655]" : "opacity-50"}`}
        />
        {!collapsed && <span className="text-sm truncate flex-1">{chat.title}</span>}
      </button>
      {!collapsed && (
        <button
          type="button"
          onClick={() => onDeleteChat(chat.id)}
          className="absolute right-2 top-1/2 -translate-y-1/2 cursor-pointer opacity-0 group-hover:opacity-100 focus-visible:opacity-100 p-1 rounded-md hover:bg-[#E10600]/15 transition-all"
          title="Delete chat"
          aria-label={`Delete chat: ${chat.title}`}
        >
          <Trash2 className="w-3.5 h-3.5 text-[#6F7789] hover:text-[#FF4655]" />
        </button>
      )}
    </div>
  );
}
