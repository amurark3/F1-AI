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
            className="fixed inset-0 bg-black/50 backdrop-blur-sm z-40 lg:hidden"
            onClick={onClose}
          />
        )}
      </AnimatePresence>

      {/* Sidebar */}
      <aside
        className={`
          fixed lg:relative top-0 left-0 z-50 lg:z-auto
          h-full shrink-0
          bg-[#0B0D0C] border-r border-[#1E2633]
          flex flex-col
          transition-all duration-200 ease-out
          ${isOpen ? "translate-x-0" : "-translate-x-full lg:translate-x-0"}
          ${collapsed ? "lg:w-[52px]" : "w-72 lg:w-64"}
        `}
      >
        {/* Header — New Chat button */}
        <div className="p-2 border-b border-[#1E2633]">
          {collapsed ? (
            <motion.button
              whileHover={{ scale: 1.05 }}
              whileTap={{ scale: 0.95 }}
              onClick={onNewChat}
              className="w-full flex items-center justify-center p-2 rounded-md bg-[#00FF78] hover:bg-white text-black transition-colors"
              title="New Chat"
            >
              <Plus className="w-4 h-4" />
            </motion.button>
          ) : (
            <motion.button
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.98 }}
              onClick={onNewChat}
              className="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-md bg-[#00FF78] hover:bg-white text-black text-sm font-black uppercase tracking-wider transition-colors duration-200"
            >
              <Plus className="w-4 h-4" />
              New Chat
            </motion.button>
          )}
        </div>

        {/* Chat list */}
        <div className="flex-1 overflow-y-auto py-2">
          {chats.length === 0
            ? !collapsed && (
                <p className="text-center text-neutral-500 italic text-xs py-8 px-4">No conversations yet</p>
              )
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
              text-neutral-500 hover:text-neutral-200 hover:bg-white/[0.04]
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
        group relative mx-2 mb-1 rounded-md transition-colors duration-200
        ${
          isActive
            ? "bg-[#00FF78]/10 text-white border border-[#00FF78]/25"
            : "text-neutral-400 hover:bg-white/[0.04] hover:text-neutral-200 border border-transparent"
        }
      `}
    >
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
        {collapsed ? (
          <MessageSquare className={`w-4 h-4 ${isActive ? "opacity-100" : "opacity-50"}`} />
        ) : (
          <>
            <MessageSquare className="w-4 h-4 shrink-0 mr-2.5 opacity-50" />
            <span className="text-sm truncate flex-1">{chat.title}</span>
          </>
        )}
      </button>
      {!collapsed && (
        <button
          type="button"
          onClick={() => onDeleteChat(chat.id)}
          className="absolute right-2 top-1/2 -translate-y-1/2 cursor-pointer opacity-0 group-hover:opacity-100 focus-visible:opacity-100 p-1 rounded-md hover:bg-[#E10600]/15 transition-all"
          title="Delete chat"
          aria-label={`Delete chat: ${chat.title}`}
        >
          <Trash2 className="w-3.5 h-3.5 text-neutral-500 hover:text-[#E10600]" />
        </button>
      )}
    </div>
  );
}
