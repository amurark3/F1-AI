"use client";

import ChatSidebar from './ChatSidebar';
import ChatWelcome from './ChatWelcome';
import ChatMessages from './ChatMessages';
import ChatInput from './ChatInput';
import { useChat } from '../hooks/useChat';

export default function ChatScreen() {
  const {
    chats,
    activeChatId,
    activeChat,
    messages,
    input,
    isLoading,
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
  } = useChat();

  const hasMessages = messages.length > 0;

  return (
    <div className="flex" style={{ height: 'calc(100vh - 56px)' }}>
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

      <div className="flex-1 flex flex-col min-w-0">
        {/* Mobile sidebar toggle */}
        <div className="lg:hidden flex items-center px-4 py-2 border-b border-neutral-800/40">
          <button
            onClick={() => setSidebarOpen(true)}
            className="p-2 rounded-lg hover:bg-neutral-800 text-neutral-400 transition-colors"
          >
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 6.75h16.5M3.75 12h16.5m-16.5 5.25h16.5" />
            </svg>
          </button>
          <span className="ml-3 text-sm text-neutral-500 truncate">
            {activeChat?.title ?? 'New Chat'}
          </span>
        </div>

        {/* Messages or welcome */}
        <div className="flex-1 overflow-y-auto">
          {hasMessages ? (
            <ChatMessages
              messages={messages}
              isLoading={isLoading}
              messagesEndRef={messagesEndRef}
            />
          ) : (
            <ChatWelcome
              onSelectPrompt={sendMessage}
              disabled={isLoading}
            />
          )}
        </div>

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
