"use client";

import { MessageSquare, Plus, Trash2, PanelLeftClose, PanelLeftOpen } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { Chat } from '../hooks/useLocalChats';

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
          glass-strong border-r border-white/5
          flex flex-col
          transition-all duration-200 ease-out
          ${isOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'}
          ${collapsed ? 'lg:w-[52px]' : 'w-72 lg:w-64'}
        `}
      >
        {/* Header — New Chat button */}
        <div className="p-2 border-b border-white/5">
          {collapsed ? (
            <motion.button
              whileHover={{ scale: 1.05 }}
              whileTap={{ scale: 0.95 }}
              onClick={onNewChat}
              className="w-full flex items-center justify-center p-2 rounded-xl bg-gradient-to-r from-red-600 to-orange-500 hover:from-red-500 hover:to-orange-400 text-white shadow-lg shadow-red-600/20 transition-colors"
              title="New Chat"
            >
              <Plus className="w-4 h-4" />
            </motion.button>
          ) : (
            <motion.button
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.98 }}
              onClick={onNewChat}
              className="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl bg-gradient-to-r from-red-600 to-orange-500 hover:from-red-500 hover:to-orange-400 text-white text-sm font-bold uppercase tracking-wider shadow-lg shadow-red-600/20 hover:shadow-red-500/30 transition-all duration-300"
            >
              <Plus className="w-4 h-4" />
              New Chat
            </motion.button>
          )}
        </div>

        {/* Chat list */}
        <div className="flex-1 overflow-y-auto py-2">
          {chats.length === 0 ? (
            !collapsed && (
              <p className="text-center text-neutral-500 italic text-xs py-8 px-4">
                No conversations yet
              </p>
            )
          ) : (
            chats.map((chat) => (
              <div
                key={chat.id}
                className={`
                  group relative mx-2 mb-1 rounded-xl cursor-pointer transition-all duration-200
                  ${activeChatId === chat.id
                    ? 'bg-white/8 text-white border border-white/10'
                    : 'text-neutral-400 hover:bg-white/5 hover:text-neutral-200 border border-transparent'
                  }
                `}
                onClick={() => {
                  onSelectChat(chat.id);
                  onClose();
                }}
                title={collapsed ? chat.title : undefined}
              >
                {collapsed ? (
                  <div className="flex items-center justify-center p-2">
                    <MessageSquare className={`w-4 h-4 ${activeChatId === chat.id ? 'opacity-100' : 'opacity-50'}`} />
                  </div>
                ) : (
                  <div className="flex items-center px-3 py-2.5">
                    <MessageSquare className="w-4 h-4 shrink-0 mr-2.5 opacity-50" />
                    <span className="text-sm truncate flex-1">{chat.title}</span>
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        onDeleteChat(chat.id);
                      }}
                      className="opacity-0 group-hover:opacity-100 p-1 rounded-lg hover:bg-red-500/20 transition-all shrink-0 ml-1"
                      title="Delete chat"
                    >
                      <Trash2 className="w-3.5 h-3.5 text-neutral-500 hover:text-red-400" />
                    </button>
                  </div>
                )}
              </div>
            ))
          )}
        </div>

        {/* Footer — Collapse toggle (desktop only) */}
        <div className="hidden lg:block border-t border-white/5 p-2">
          <button
            onClick={onToggleCollapse}
            className={`
              w-full flex items-center gap-2 p-2 rounded-xl
              text-neutral-500 hover:text-neutral-200 hover:bg-white/5
              transition-all duration-200 text-xs
              ${collapsed ? 'justify-center' : 'justify-between'}
            `}
            title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          >
            {!collapsed && <span className="font-medium">Collapse</span>}
            {collapsed ? <PanelLeftOpen className="w-4 h-4" /> : <PanelLeftClose className="w-4 h-4" />}
          </button>
        </div>
      </aside>
    </>
  );
}
