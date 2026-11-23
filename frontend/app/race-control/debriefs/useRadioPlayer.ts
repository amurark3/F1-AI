"use client";

import { useCallback, useEffect, useRef, useState } from "react";

export interface NowPlaying {
  url: string | null;
  playing: boolean;
  elapsed: number;
  duration: number | null;
}

const IDLE: NowPlaying = { url: null, playing: false, elapsed: 0, duration: null };

export interface RadioPlayer {
  now: NowPlaying;
  failed: ReadonlySet<string>;
  toggle: (url: string) => void;
}

function finiteDuration(el: HTMLAudioElement): number | null {
  return Number.isFinite(el.duration) ? el.duration : null;
}

/**
 * One audio element for the whole section, so one clip plays at a time.
 *
 * The element is made on the first play and never attached to the page: a clip
 * has no captions to offer (the audio has no transcript), so there is no
 * `<audio>` in the markup. Leaving the page pauses it.
 */
export function useRadioPlayer(): RadioPlayer {
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const urlRef = useRef("");
  const [now, setNow] = useState<NowPlaying>(IDLE);
  const [failed, setFailed] = useState<ReadonlySet<string>>(new Set());

  useEffect(
    () => () => {
      audioRef.current?.pause();
    },
    [],
  );

  const element = useCallback((): HTMLAudioElement => {
    if (audioRef.current) return audioRef.current;
    const el = new Audio();
    el.preload = "none";
    const duration = () => setNow((current) => ({ ...current, duration: finiteDuration(el) }));
    el.addEventListener("play", () => setNow((current) => ({ ...current, playing: true })));
    el.addEventListener("pause", () => setNow((current) => ({ ...current, playing: false })));
    el.addEventListener("timeupdate", () => setNow((current) => ({ ...current, elapsed: el.currentTime })));
    el.addEventListener("loadedmetadata", duration);
    el.addEventListener("durationchange", duration);
    const idle = () => {
      urlRef.current = "";
      setNow(IDLE);
    };
    el.addEventListener("ended", idle);
    el.addEventListener("error", () => {
      const broken = urlRef.current;
      setFailed((current) => new Set([...current, broken]));
      idle();
    });
    audioRef.current = el;
    return el;
  }, []);

  const toggle = useCallback(
    (url: string) => {
      const el = element();
      if (urlRef.current === url && !el.paused) {
        el.pause();
        return;
      }
      if (urlRef.current !== url) {
        urlRef.current = url;
        el.src = url;
        setNow({ url, playing: true, elapsed: 0, duration: null });
      }
      // Switching clips rejects the old play() with AbortError: only the current clip resets.
      el.play().catch(() => {
        if (urlRef.current !== url) return;
        urlRef.current = "";
        setNow(IDLE);
      });
    },
    [element],
  );

  return { now, failed, toggle };
}
