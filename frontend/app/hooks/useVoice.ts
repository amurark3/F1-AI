"use client";

import { useCallback, useEffect, useRef, useState } from "react";

/**
 * Browser voice I/O for the race-engineer chat — speech-to-text (dictate a
 * question) and text-to-speech (hear the reply in a team-radio cadence).
 *
 * Uses the Web Speech API entirely client-side (no backend, no cost). Degrades
 * gracefully: `supported` is false where the API is unavailable, and every
 * method is a safe no-op in that case.
 */

// Minimal typings for the non-standard Web Speech API (not in lib.dom).
interface SpeechRecognitionResultLike {
  0: { transcript: string };
  isFinal: boolean;
}
interface SpeechRecognitionEventLike {
  results: ArrayLike<SpeechRecognitionResultLike>;
}
interface SpeechRecognitionLike {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  onresult: ((event: SpeechRecognitionEventLike) => void) | null;
  onend: (() => void) | null;
  onerror: (() => void) | null;
  start: () => void;
  stop: () => void;
}
type SpeechRecognitionCtor = new () => SpeechRecognitionLike;

interface UseVoiceOptions {
  onTranscript?: (text: string) => void;
}

export interface UseVoiceResult {
  supported: boolean;
  listening: boolean;
  speaking: boolean;
  startListening: () => void;
  stopListening: () => void;
  speak: (text: string) => void;
  cancelSpeech: () => void;
}

function getRecognitionCtor(): SpeechRecognitionCtor | null {
  if (typeof window === "undefined") return null;
  const w = window as unknown as {
    SpeechRecognition?: SpeechRecognitionCtor;
    webkitSpeechRecognition?: SpeechRecognitionCtor;
  };
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
}

/** Strip markdown/table noise so TTS reads clean prose, not symbols. */
function cleanForSpeech(text: string): string {
  return text
    .replace(/\[TOOL_(START|END)\][^[]*\[\/TOOL_(START|END)\]/g, " ")
    .replace(/```[\s\S]*?```/g, " ")
    .replace(/\|/g, " ")
    .replace(/[#*_`>]/g, "")
    .replace(/\s+/g, " ")
    .trim();
}

export function useVoice(options: UseVoiceOptions = {}): UseVoiceResult {
  const { onTranscript } = options;
  const [listening, setListening] = useState(false);
  const [speaking, setSpeaking] = useState(false);
  const recognitionRef = useRef<SpeechRecognitionLike | null>(null);

  const hasRecognition = getRecognitionCtor() !== null;
  const hasSynthesis = typeof window !== "undefined" && "speechSynthesis" in window;
  const supported = hasRecognition || hasSynthesis;

  const onTranscriptRef = useRef(onTranscript);
  useEffect(() => {
    onTranscriptRef.current = onTranscript;
  }, [onTranscript]);

  const startListening = useCallback(() => {
    const Ctor = getRecognitionCtor();
    if (!Ctor || listening) return;
    const recognition = new Ctor();
    recognition.lang = "en-US";
    recognition.continuous = false;
    recognition.interimResults = false;
    recognition.onresult = (event) => {
      const transcript = Array.from({ length: event.results.length }, (_, i) => event.results[i][0].transcript)
        .join(" ")
        .trim();
      if (transcript) onTranscriptRef.current?.(transcript);
    };
    recognition.onend = () => setListening(false);
    recognition.onerror = () => setListening(false);
    recognitionRef.current = recognition;
    setListening(true);
    recognition.start();
  }, [listening]);

  const stopListening = useCallback(() => {
    recognitionRef.current?.stop();
    setListening(false);
  }, []);

  const speak = useCallback(
    (text: string) => {
      if (!hasSynthesis) return;
      const clean = cleanForSpeech(text);
      if (!clean) return;
      window.speechSynthesis.cancel();
      const utterance = new SpeechSynthesisUtterance(clean);
      utterance.rate = 1.06; // slightly brisk, like radio
      utterance.pitch = 1.0;
      utterance.onstart = () => setSpeaking(true);
      utterance.onend = () => setSpeaking(false);
      utterance.onerror = () => setSpeaking(false);
      window.speechSynthesis.speak(utterance);
    },
    [hasSynthesis],
  );

  const cancelSpeech = useCallback(() => {
    if (hasSynthesis) window.speechSynthesis.cancel();
    setSpeaking(false);
  }, [hasSynthesis]);

  // Stop everything on unmount.
  useEffect(() => {
    return () => {
      recognitionRef.current?.stop();
      if (typeof window !== "undefined" && "speechSynthesis" in window) {
        window.speechSynthesis.cancel();
      }
    };
  }, []);

  return { supported, listening, speaking, startListening, stopListening, speak, cancelSpeech };
}
