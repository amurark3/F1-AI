# Coding Conventions

**Analysis Date:** 2026-02-16

## Naming Patterns

**Files:**
- React components: PascalCase with `.tsx` extension (e.g., `ChatMessages.tsx`, `RaceCard.tsx`)
- Custom hooks: camelCase with `use` prefix and `.ts` extension (e.g., `useChat.ts`, `useLocalChats.ts`)
- Constants/utilities: camelCase with `.ts` extension (e.g., `fetcher.ts`, `api.ts`)
- Python modules: snake_case with `.py` extension (e.g., `routes.py`, `tools.py`, `circuits.py`)
- Python directories: snake_case (e.g., `app/api`, `app/rag`)

**Functions:**
- React components: PascalCase (exported default or named exports)
- React hooks: camelCase with `use` prefix (e.g., `useChat()`, `useLocalChats()`)
- Utility functions: camelCase (e.g., `fetcher()`, `fetcherWithTimeout()`)
- Helper functions (internal): camelCase with optional `_` prefix for private (e.g., `_fmt_timedelta()`)
- Python tool decorators: snake_case (e.g., `get_track_conditions()`, `perform_web_search()`)

**Variables:**
- React component props: camelCase and typed with interfaces (e.g., `isLoading`, `toolStatus`)
- State variables: camelCase (e.g., `activeChatId`, `messages`)
- Constants: UPPER_SNAKE_CASE in Python (e.g., `STORAGE_KEY`, `CIRCUIT_DATA`)
- Local variables: camelCase

**Types:**
- TypeScript interfaces: PascalCase (e.g., `ChatMessagesProps`, `Message`, `RaceEvent`)
- TypeScript type aliases: PascalCase
- Python type hints: Use built-in types and collections (e.g., `dict[str, dict]`, `List[dict]`)

## Code Style

**Formatting:**
- ESLint with Next.js config: `eslint-config-next` (Core Web Vitals + TypeScript)
- Config file: `/Users/adityamurarka/Desktop/F1-AI/frontend/eslint.config.mjs`
- Applies to all `.tsx` and `.ts` files
- No Prettier config detected; ESLint is the authority for formatting

**Linting:**
- ESLint 9 with Next.js core-web-vitals and typescript presets
- Enforces React best practices and type safety
- Command: `npm run lint` in frontend directory
- Python: No formal linting config detected; follows implicit PEP 8 patterns

## Import Organization

**Order:**
1. Third-party libraries and React imports (e.g., `import { useState }`, `import useSWR`)
2. Relative imports from project (e.g., `import { useChat } from './useLocalChats'`)
3. Type imports (e.g., `import { type Message }`)

**Path Aliases:**
- TypeScript: `@/*` maps to root of frontend directory (`./`)
- Used in imports: `import NavShell from '@/app/components/NavShell'`
- Configured in: `/Users/adityamurarka/Desktop/F1-AI/frontend/tsconfig.json`

**Examples from codebase:**
```typescript
// TypeScript example from ChatMessages.tsx
import { type RefObject } from 'react';
import { Loader2, RefreshCw } from 'lucide-react';
import { motion } from 'framer-motion';
import { type Message } from '../hooks/useLocalChats';
```

```python
# Python example from routes.py
import os
import asyncio
import threading
import pandas as pd
import fastf1
from fastapi import APIRouter
from pydantic import BaseModel
from typing import List
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, ToolMessage
```

## Error Handling

**Patterns:**
- React: Try-catch blocks in async functions, errors surfaced to UI
- API errors: `if (!response.ok) throw new Error(...)` pattern in fetchers
- Tools (Python): Catch exceptions and return error messages as strings for LLM processing
- Generator functions: Wrap in try-catch, yield error text to client

**Examples:**
```typescript
// Frontend error handling in useChat.ts
try {
  const response = await fetch(`${API_BASE}/api/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ messages: [...messages, userMessage] }),
  });
  if (!response.ok) throw new Error(`Server error: ${response.status}`);
  if (!response.body) throw new Error('No response stream received.');
} catch (error) {
  console.error('Chat error:', error);
  const errMsg = `**Connection Error:** Could not reach the backend...`;
  setMessages((prev) => [...prev, { role: 'assistant', content: errMsg }]);
}
```

```python
# Backend error handling in routes.py (generate function)
try:
  # ... agentic loop
except asyncio.TimeoutError:
  tool_result = f"Tool '{tool_name}' timed out after 30 seconds."
except Exception as tool_err:
  tool_result = f"Error executing tool '{tool_name}': {tool_err}"
```

## Logging

**Framework:** `console.error()` and `print()` statements

**Patterns:**
- React: `console.error()` for client-side errors and debugging
- Python: `print()` with emoji prefixes for operation status (e.g., `print(f"📦 Prefetching...")`)
- Backend tool functions: Print operation name and results preview (max 80 chars)

**Examples:**
```python
# From routes.py and tools.py
print("🤖 ASKING MODEL...")
print(f"🔄 TURN {turn_count}: Model requested {len(current_response.tool_calls)} tool(s).")
print(f"🛠️  EXECUTING: {tool_name} with args {tool_args}")
print(f"✅ RESULT (preview): {str(tool_result)[:80]}...")
print(f"⏱️ TOOL TIMEOUT: {tool_name}")
print(f"❌ CRITICAL ERROR IN GENERATE: {e}")
```

## Comments

**When to Comment:**
- Above complex logic that isn't self-evident
- Explaining why a choice was made (not what the code does)
- Docstrings for functions explaining purpose, parameters, and return values
- Block comments for multi-function sections (e.g., "Request / Response models")

**JSDoc/TSDoc:**
- Used in React components with prop interfaces
- Used in utility functions (e.g., fetcher documentation)
- Format: `/** description */` above function declarations

**Example:**
```typescript
/**
 * SWR-compatible fetch wrapper used by all data-fetching hooks.
 *
 * Throws an error for non-2xx HTTP responses so SWR can surface them
 * via the `error` return value rather than silently receiving bad JSON.
 */
export const fetcher = (url: string) =>
  fetch(url).then((res) => {
    if (!res.ok) {
      throw new Error(`Request failed: ${res.status} ${res.statusText}`);
    }
    return res.json();
  });
```

```python
def _fmt_timedelta(time_val) -> str:
    """
    Converts a pandas Timedelta (or NaT) to a clean lap-time string.

    Examples:
      0 days 00:01:23.456 → "1:23.456"
      0 days 00:00:45.123 → "45.123"
      NaT                 → "-"
    """
```

## Function Design

**Size:**
- React components: Keep under 300 lines; split complex logic into sub-components or custom hooks
- Utility functions: Single responsibility; one function per concern
- Python tools: Each tool function (decorated with `@tool`) has one clear purpose

**Parameters:**
- React components: Use a single props object typed with an interface
- Custom hooks: No parameters expected; state management internal
- Utility functions: Explicit parameters with type annotations
- Python tools: Type-hinted parameters; some have defaults (e.g., `timeoutMs = 35000`)

**Return Values:**
- React components: Return JSX element
- Hooks: Return object with state, refs, and action functions
- Utility functions: Return data (parsed JSON, error, or computed value)
- Python tools: Return string (for LLM consumption) or structured data (dict)

**Examples:**
```typescript
// React component with typed props
interface ChatMessagesProps {
  messages: Message[];
  isLoading: boolean;
  toolStatus: string | null;
  messagesEndRef: RefObject<HTMLDivElement | null>;
  onRegenerate?: () => void;
}

export default function ChatMessages({ messages, isLoading, toolStatus, messagesEndRef, onRegenerate }: ChatMessagesProps) {
  // ... component logic
}

// Custom hook return object
return {
  // State
  chats,
  activeChatId,
  messages,
  // Refs
  messagesEndRef,
  inputRef,
  // Actions
  setInput,
  sendMessage,
  handleSubmit,
};
```

```python
# Python tool with type hints
@tool
def get_sprint_results(year: int, grand_prix: str):
    """Fetches SATURDAY SPRINT RACE results (the short 100 km race)."""
    # ... implementation
    return "\n".join(summary)  # Returns markdown table as string
```

## Module Design

**Exports:**
- React components: Single default export for the main component
- Utilities: Named exports for functions and constants (e.g., `export const fetcher`)
- Custom hooks: Single named export (e.g., `export function useChat()`)
- Python modules: Use `@tool` decorator to register functions; export `TOOL_LIST` and `TOOL_MAP`

**Barrel Files:**
- Not used in this codebase; imports are direct from source files
- Example of pattern to avoid: Creating index.ts files that re-export multiple components

**Examples:**
```typescript
// frontend/app/utils/fetcher.ts — named exports
export const fetcher = (url: string) => { ... };
export const fetcherWithTimeout = (url: string, timeoutMs = 35000) => { ... };

// frontend/app/components/ChatMessages.tsx — default export
export default function ChatMessages({ ... }) { ... }

// frontend/app/hooks/useChat.ts — named export (function)
export function useChat() { ... }
```

```python
# backend/app/api/tools.py
# Functions decorated with @tool are registered
TOOL_LIST = [get_track_conditions, perform_web_search, get_sprint_results, ...]
TOOL_MAP = {
    "get_track_conditions": get_track_conditions,
    "perform_web_search": perform_web_search,
    ...
}
```

## Component Patterns

**Sub-Components:**
- Small, single-purpose components defined within the same file (e.g., `TypingIndicator` and `MessageBubble` in `ChatMessages.tsx`)
- Not exported; for internal use only
- Receive props as arguments

**State Management:**
- Local state with `useState()` for component-level concerns
- Custom hooks (`useChat`, `useLocalChats`) for shared or complex state
- localStorage integration via custom hooks for persistence

**Async Operations:**
- Streaming responses with `fetch().body.getReader()` and `TextDecoder`
- SWR for data fetching with timeouts and error handling
- AsyncIO in Python with `asyncio.to_thread()` for blocking I/O

---

*Convention analysis: 2026-02-16*
