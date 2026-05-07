"use client";

import { useState, useCallback, useEffect, useRef } from 'react';

interface ToastState {
  message: string;
  onRetry?: () => void;
}

export const useToast = () => {
  const [toast, setToast] = useState<ToastState | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const showToast = useCallback((message: string, onRetry?: () => void) => {
    if (timerRef.current) clearTimeout(timerRef.current);
    setToast({ message, onRetry });
    timerRef.current = setTimeout(() => setToast(null), 4000);
  }, []);

  const dismissToast = useCallback(() => {
    if (timerRef.current) clearTimeout(timerRef.current);
    setToast(null);
  }, []);

  useEffect(() => () => {
    if (timerRef.current) clearTimeout(timerRef.current);
  }, []);

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
