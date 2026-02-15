"use client";

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

const ChatIcon = ({ className = "w-4 h-4" }: { className?: string }) => (
  <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
    <path strokeLinecap="round" strokeLinejoin="round" d="M8.625 12a.375.375 0 1 1-.75 0 .375.375 0 0 1 .75 0Zm0 0H8.25m4.125 0a.375.375 0 1 1-.75 0 .375.375 0 0 1 .75 0Zm0 0H12m4.125 0a.375.375 0 1 1-.75 0 .375.375 0 0 1 .75 0Zm0 0h-.375M21 12c0 4.556-4.03 8.25-9 8.25a9.764 9.764 0 0 1-2.555-.337A5.972 5.972 0 0 1 5.41 20.97a5.969 5.969 0 0 1-.474-.065 4.48 4.48 0 0 0 .978-2.025c.09-.457-.133-.901-.467-1.226C3.93 16.178 3 14.189 3 12c0-4.556 4.03-8.25 9-8.25s9 3.694 9 8.25Z" />
  </svg>
);

const ChevronLeft = () => (
  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
    <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 19.5 8.25 12l7.5-7.5" />
  </svg>
);

const ChevronRight = () => (
  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
    <path strokeLinecap="round" strokeLinejoin="round" d="m8.25 4.5 7.5 7.5-7.5 7.5" />
  </svg>
);

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
      {isOpen && (
        <div
          className="fixed inset-0 bg-black/60 z-40 lg:hidden"
          onClick={onClose}
        />
      )}

      {/* Sidebar */}
      <aside
        className={`
          fixed lg:relative top-0 left-0 z-50 lg:z-auto
          h-full shrink-0
          bg-neutral-950 border-r border-neutral-800/60
          flex flex-col
          transition-all duration-200 ease-out
          ${isOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'}
          ${collapsed ? 'lg:w-[52px]' : 'w-72 lg:w-64'}
        `}
      >
        {/* Header — New Chat button */}
        <div className="p-2 border-b border-neutral-800/60">
          {collapsed ? (
            <button
              onClick={onNewChat}
              className="w-full flex items-center justify-center p-2 rounded-lg bg-red-600 hover:bg-red-500 text-white transition-colors"
              title="New Chat"
            >
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" />
              </svg>
            </button>
          ) : (
            <button
              onClick={onNewChat}
              className="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg bg-red-600 hover:bg-red-500 text-white text-sm font-bold uppercase tracking-wider transition-colors"
            >
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" />
              </svg>
              New Chat
            </button>
          )}
        </div>

        {/* Chat list */}
        <div className="flex-1 overflow-y-auto py-2">
          {chats.length === 0 ? (
            !collapsed && (
              <p className="text-center text-neutral-600 text-xs py-8 px-4">
                No conversations yet
              </p>
            )
          ) : (
            chats.map((chat) => (
              <div
                key={chat.id}
                className={`
                  group relative mx-1.5 mb-0.5 rounded-lg cursor-pointer transition-colors
                  ${activeChatId === chat.id
                    ? 'bg-neutral-800 text-white'
                    : 'text-neutral-400 hover:bg-neutral-900 hover:text-neutral-200'
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
                    <ChatIcon className={`w-4 h-4 ${activeChatId === chat.id ? 'opacity-100' : 'opacity-50'}`} />
                  </div>
                ) : (
                  <div className="flex items-center px-3 py-2.5">
                    <ChatIcon className="w-4 h-4 shrink-0 mr-2.5 opacity-50" />
                    <span className="text-sm truncate flex-1">{chat.title}</span>
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        onDeleteChat(chat.id);
                      }}
                      className="opacity-0 group-hover:opacity-100 p-1 rounded hover:bg-neutral-700 transition-all shrink-0 ml-1"
                      title="Delete chat"
                    >
                      <svg className="w-3.5 h-3.5 text-neutral-500 hover:text-red-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="m14.74 9-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 0 1-2.244 2.077H8.084a2.25 2.25 0 0 1-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 0 0-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 0 1 3.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 0 0-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 0 0-7.5 0" />
                      </svg>
                    </button>
                  </div>
                )}
              </div>
            ))
          )}
        </div>

        {/* Footer — Collapse toggle (desktop only) */}
        <div className="hidden lg:block border-t border-neutral-800/60 p-2">
          <button
            onClick={onToggleCollapse}
            className={`
              w-full flex items-center gap-2 p-2 rounded-lg
              text-neutral-500 hover:text-neutral-200 hover:bg-neutral-800/60
              transition-colors text-xs
              ${collapsed ? 'justify-center' : 'justify-between'}
            `}
            title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          >
            {!collapsed && <span className="font-medium">Collapse</span>}
            {collapsed ? <ChevronRight /> : <ChevronLeft />}
          </button>
        </div>
      </aside>
    </>
  );
}
