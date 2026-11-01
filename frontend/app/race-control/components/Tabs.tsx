"use client";

import { useRef, type KeyboardEvent, type ReactNode } from "react";

export interface TabItem<K extends string> {
  key: K;
  label: ReactNode;
  /** Tooltip, for what the tab holds. */
  title?: string;
  disabled?: boolean;
}

interface TabsProps<K extends string> {
  items: ReadonlyArray<TabItem<K>>;
  active: K;
  onChange: (key: K) => void;
  /** Ties each tab to its panel; unique on the page. */
  idPrefix: string;
  /** What the tabs choose between, for screen readers. */
  label: string;
  variant?: "underline" | "segmented";
}

const MOVES: Record<string, (index: number, count: number) => number> = {
  ArrowRight: (index, count) => (index + 1) % count,
  ArrowLeft: (index, count) => (index - 1 + count) % count,
  Home: () => 0,
  End: (_index, count) => count - 1,
};

const VARIANT_STYLES = {
  underline: {
    list: "flex gap-1 overflow-x-auto border-b border-[#1E2633]",
    tab: "relative shrink-0 px-4 py-3 text-sm",
    on: "text-white",
    off: "text-[#6F7789] hover:text-[#D7DBE7]",
  },
  segmented: {
    list: "inline-flex max-w-full gap-1 overflow-x-auto rounded-md border border-[#1E2633] bg-[#0D111B] p-1",
    tab: "shrink-0 rounded px-3 py-1.5 font-mono text-[11px] font-bold uppercase tracking-[0.14em]",
    on: "bg-[#E10600]/15 text-white",
    off: "text-[#6F7789] hover:text-[#D7DBE7]",
  },
} as const;

export function tabId(idPrefix: string, key: string): string {
  return `${idPrefix}-tab-${key}`;
}

export function panelId(idPrefix: string): string {
  return `${idPrefix}-panel`;
}

/**
 * A row of tabs that follows the WAI-ARIA tabs pattern: one tab stop, arrow
 * keys (and Home/End) move between tabs, and each tab names the panel it
 * controls. Pair with {@link TabPanel} using the same `idPrefix`.
 */
export function Tabs<K extends string>({
  items,
  active,
  onChange,
  idPrefix,
  label,
  variant = "underline",
}: TabsProps<K>) {
  const refs = useRef<Array<HTMLButtonElement | null>>([]);
  const styles = VARIANT_STYLES[variant];
  const enabled = items.filter((item) => !item.disabled);

  const onKeyDown = (event: KeyboardEvent<HTMLButtonElement>, key: K) => {
    const move = MOVES[event.key];
    if (!move || enabled.length === 0) return;
    event.preventDefault();
    const current = Math.max(
      0,
      enabled.findIndex((item) => item.key === key),
    );
    const next = enabled[move(current, enabled.length)];
    onChange(next.key);
    refs.current[items.indexOf(next)]?.focus();
  };

  return (
    <div role="tablist" aria-label={label} className={styles.list}>
      {items.map((item, index) => {
        const selected = item.key === active;
        return (
          <button
            key={item.key}
            ref={(node) => {
              refs.current[index] = node;
            }}
            type="button"
            role="tab"
            id={tabId(idPrefix, item.key)}
            aria-selected={selected}
            aria-controls={panelId(idPrefix)}
            tabIndex={selected ? 0 : -1}
            disabled={item.disabled}
            title={item.title}
            onClick={() => onChange(item.key)}
            onKeyDown={(event) => onKeyDown(event, item.key)}
            className={`${styles.tab} transition-colors disabled:cursor-not-allowed disabled:opacity-40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#E10600]/50 ${
              selected ? styles.on : styles.off
            }`}
          >
            {item.label}
            {variant === "underline" && selected && (
              <span className="absolute inset-x-0 bottom-0 h-[2px] bg-[#E10600]" aria-hidden="true" />
            )}
          </button>
        );
      })}
    </div>
  );
}

/** The content the selected tab controls. */
export function TabPanel({
  idPrefix,
  active,
  children,
  className = "",
}: {
  idPrefix: string;
  active: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <div role="tabpanel" id={panelId(idPrefix)} aria-labelledby={tabId(idPrefix, active)} className={className}>
      {children}
    </div>
  );
}
