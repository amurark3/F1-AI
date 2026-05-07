"use client";

import { useState, useCallback } from 'react';

interface ToastState {
  message: string;
  onRetry?: () => void;
}

export const useToast = () => {
  const [toast, setToast] = useState<ToastState | null>(null);

  const showToast = useCallback((message: string, onRetry?: () => void) => {
    setToast({ message, onRetry });
    const timer = setTimeout(() => setToast(null), 4000);
    // Return a cleanup function in case component unmounts
    return () => clearTimeout(timer);
  }, []);

  const dismissToast = useCallback(() => setToast(null), []);

  return { toast, showToast, dismissToast };
};

interface ToastProps {
  message: string;
  onRetry?: () => void;
  onDismiss: () => void;
}

export const Toast = ({ message, onRetry, onDismiss }: ToastProps) => (
  <div className="fixed bottom-4 right-4 z-50 flex items-center gap-3 glass rounded-2xl px-4 py-3 shadow-xl shadow-black/40 max-w-sm">
    <span className="text-sm text-white leading-snug flex-1">{message}</span>
    {onRetry && (
      <button
        onClick={() => { onRetry(); onDismiss(); }}
        className="text-xs font-bold text-red-400 hover:text-red-300 transition-colors shrink-0"
      >
        Retry
      </button>
    )}
  </div>
);
