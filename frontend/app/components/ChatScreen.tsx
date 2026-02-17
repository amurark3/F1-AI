"use client";

import { PanelLeftOpen } from 'lucide-react';
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
        <div className="lg:hidden flex items-center px-4 py-2 border-b border-white/5 bg-neutral-950/50 backdrop-blur-sm">
          <button
            onClick={() => setSidebarOpen(true)}
            className="p-2 rounded-xl hover:bg-white/5 text-neutral-500 hover:text-white transition-all duration-200"
          >
            <PanelLeftOpen className="w-5 h-5" />
          </button>
          <span className="ml-3 text-sm text-neutral-400 font-medium truncate">
            {activeChat?.title ?? 'New Chat'}
          </span>
        </div>

        {/* Messages or welcome */}
        <div className="flex-1 overflow-y-auto">
          {hasMessages ? (
            <ChatMessages
              messages={messages}
              isLoading={isLoading}
              toolStatus={toolStatus}
              messagesEndRef={messagesEndRef}
              onRegenerate={regenerate}
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
