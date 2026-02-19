# Testing Patterns

**Analysis Date:** 2026-02-16

## Test Framework

**Status:** Not Detected

**Current State:**
- No Jest, Vitest, Pytest, or similar test runner is configured in the codebase
- Frontend package.json contains no test scripts
- Backend requirements.txt contains no testing frameworks
- No `.test.ts`, `.spec.ts`, `.test.py`, or `.spec.py` files exist outside node_modules

**Implication:** All code changes must be verified manually or through integration testing. No automated test suite is in place.

## When Tests Should Be Added

**Critical areas to test first (high risk, no coverage):**

1. **Data Fetching & Streaming (`frontend/app/hooks/useChat.ts`)**
   - Stream parsing logic for `[TOOL_START]` / `[TOOL_END]` markers
   - Error handling when backend is unreachable
   - Message deduplication during streaming
   - Chat persistence to localStorage

2. **Time Zone Conversions (`frontend/app/components/RaceCard.tsx`)**
   - Date parsing with and without timezone offsets
   - Countdown calculations with edge cases (dates in past, exact now)
   - Session formatting in different timezones

3. **Agentic Loop (`backend/routes.py` - `generate()` function)**
   - Tool call parsing and execution
   - Max-turn limit enforcement
   - Error recovery when tools fail
   - Streaming response chunking

4. **Tool Functions (`backend/app/api/tools.py`)**
   - Each `@tool` decorated function should validate inputs and handle missing data
   - Markdown table formatting (especially for Qualifying with Q1/Q2/Q3 splits)
   - Timeout handling (30-second limit on tool execution)

5. **State Management (`frontend/app/hooks/useLocalChats.ts`)**
   - localStorage read/write operations
   - Chat creation with unique IDs
   - Message ordering (new chats at top)
   - Chat deletion cascading

## Suggested Test Structure

### For Frontend (TypeScript/React)

**Recommended Framework:** Vitest (lightweight, Vite-native)

**Test File Organization:**
```
frontend/app/
├── hooks/
│   ├── useChat.ts
│   └── useChat.test.ts          # Co-located with implementation
├── utils/
│   ├── fetcher.ts
│   └── fetcher.test.ts
└── components/
    ├── ChatMessages.tsx
    └── ChatMessages.test.tsx
```

**Installation command:**
```bash
npm install --save-dev vitest @vitest/ui @testing-library/react @testing-library/jest-dom
```

**Test Structure Example:**
```typescript
// useChat.test.ts
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { useChat } from './useChat';

describe('useChat', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
  });

  it('should initialize with empty chat state', () => {
    const { result } = renderHook(() => useChat());
    expect(result.current.messages).toEqual([]);
    expect(result.current.activeChatId).toBeNull();
  });

  it('should create a new chat on first message', async () => {
    const { result } = renderHook(() => useChat());

    await act(async () => {
      result.current.setInput('Hello');
      await result.current.handleSubmit({ preventDefault: () => {} });
    });

    await waitFor(() => {
      expect(result.current.activeChatId).not.toBeNull();
      expect(result.current.messages).toHaveLength(1);
    });
  });

  it('should parse tool status markers from stream', async () => {
    // Mock fetch to return a stream with [TOOL_START]/[TOOL_END] markers
    // Verify that toolStatus is set correctly
  });
});
```

### For Backend (Python)

**Recommended Framework:** Pytest

**Test File Organization:**
```
backend/app/
├── api/
│   ├── routes.py
│   ├── routes_test.py           # Or test_routes.py
│   ├── tools.py
│   └── tools_test.py
```

**Installation command:**
```bash
pip install pytest pytest-asyncio pytest-mock
```

**Test Structure Example:**
```python
# test_tools.py
import pytest
from app.api.tools import get_sprint_results, _fmt_timedelta

class TestTimeFormatting:
    """Test helper function for pandas Timedelta formatting."""

    def test_fmt_timedelta_formats_valid_time(self):
        """Should convert pandas Timedelta to clean lap-time string."""
        import pandas as pd
        td = pd.Timedelta(days=0, hours=0, minutes=1, seconds=23, milliseconds=456)
        result = _fmt_timedelta(td)
        assert result == "1:23.456"

    def test_fmt_timedelta_handles_nat(self):
        """Should return '-' for NaT (missing data)."""
        import pandas as pd
        result = _fmt_timedelta(pd.NaT)
        assert result == "-"

    def test_fmt_timedelta_trims_subsecond_precision(self):
        """Should trim to millisecond precision (max 9 chars)."""
        import pandas as pd
        td = pd.Timedelta("0 days 00:00:45.123456789")
        result = _fmt_timedelta(td)
        assert len(result) <= 9

class TestSprintResults:
    """Test get_sprint_results tool."""

    @pytest.mark.asyncio
    async def test_sprint_results_handles_missing_session(self):
        """Should return error message if session doesn't exist."""
        result = await asyncio.to_thread(
            get_sprint_results, year=2025, grand_prix="NonExistentGP"
        )
        assert "Could not fetch Sprint results" in result

    def test_sprint_results_returns_markdown_table(self):
        """Should return markdown-formatted results table."""
        # Mock fastf1.get_session() and verify output format
        result = get_sprint_results(2024, "Silverstone")
        assert "### Sprint Race Results" in result
        assert "|" in result  # Markdown table
```

## Running Tests

**Frontend (once Vitest is added):**
```bash
npm run test              # Run all tests
npm run test:watch       # Watch mode
npm run test:ui          # UI dashboard
npm run test:coverage    # Coverage report
```

**Backend (once Pytest is added):**
```bash
pytest                   # Run all tests
pytest -v               # Verbose output
pytest --cov           # Coverage report
pytest -k test_tools   # Run specific test file
pytest -x              # Stop on first failure
```

## Mocking Strategy

**Frontend Mocks:**
- Mock `fetch()` using `vi.stubGlobal()` or `MSW` (Mock Service Worker)
- Mock localStorage with `vi.mock('window.localStorage')`
- Mock timer functions with `vi.useFakeTimers()` for countdown tests
- Mock child components that have complex behavior

**Backend Mocks:**
- Mock `fastf1.get_session()` to return test data
- Mock `TavilyClient.search()` for web search tests
- Mock LLM responses for agentic loop tests
- Use `pytest-mock` fixture (`mocker`) for patching

**What to Mock:**
- External API calls (Tavily, FastF1, Gemini)
- Browser APIs (localStorage, fetch, setTimeout)
- Large data sources (race session telemetry)

**What NOT to Mock:**
- Utility functions with no side effects (e.g., date formatting)
- State management logic (test the actual hook)
- Component rendering (use `@testing-library/react` to render real components)

## Test Coverage

**Current State:** 0% (no tests exist)

**Target Coverage:**
- Hooks and utilities: 80%+
- Components: 60%+ (UI changes don't break core logic)
- Tools: 85%+ (external data sources are critical)

**View Coverage (once added):**
```bash
# Frontend
npm run test:coverage

# Backend
pytest --cov=app --cov-report=html
```

## Error Testing

**Frontend Error Pattern:**
```typescript
it('should handle fetch errors gracefully', async () => {
  vi.stubGlobal('fetch', () =>
    Promise.reject(new Error('Network failed'))
  );

  const { result } = renderHook(() => useChat());

  await act(async () => {
    result.current.setInput('test');
    await result.current.handleSubmit({ preventDefault: () => {} });
  });

  await waitFor(() => {
    const lastMessage = result.current.messages[result.current.messages.length - 1];
    expect(lastMessage.content).toContain('Connection Error');
  });
});
```

**Backend Error Pattern:**
```python
def test_tool_timeout_returns_error_message():
    """Should catch asyncio.TimeoutError and return user-friendly message."""
    with mocker.patch(
        'asyncio.wait_for',
        side_effect=asyncio.TimeoutError()
    ):
        # Call the tool or agentic loop
        result = get_some_data()
        assert "timed out" in result.lower()

def test_tool_exception_propagates_safely():
    """Should catch Exception and return message (not crash)."""
    with mocker.patch(
        'fastf1.get_session',
        side_effect=RuntimeError("FastF1 API down")
    ):
        result = get_sprint_results(2024, "Silverstone")
        assert "Could not fetch" in result
        assert "RuntimeError" not in result  # Error type hidden from user
```

## Async Testing

**Frontend Pattern (with Vitest + React Testing Library):**
```typescript
import { waitFor } from '@testing-library/react';

it('should fetch race schedule on mount', async () => {
  vi.stubGlobal('fetch', () =>
    Promise.resolve({
      ok: true,
      json: () => Promise.resolve([{ round: 1, name: 'Bahrain' }])
    })
  );

  const { result } = renderHook(() => useRaceSchedule(2025));

  await waitFor(() => {
    expect(result.current.schedule).toHaveLength(1);
  });
});
```

**Backend Pattern (with Pytest):**
```python
@pytest.mark.asyncio
async def test_chat_endpoint_streams_response(client, mocker):
    """Should stream response chunks from the generator."""
    mocker.patch('app.api.routes.llm_with_tools.ainvoke',
                 return_value=AIMessage(content="Test response"))

    response = await client.post("/api/chat", json={
        "messages": [{"role": "user", "content": "test"}]
    })

    assert response.status_code == 200
    chunks = response.body.decode().split('\n')
    assert len(chunks) > 0
```

## Fixtures and Factories

**Not Currently Used.** When tests are added, consider:

**Frontend (Vitest):**
```typescript
// vitest.config.ts — setup fixtures
import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./vitest.setup.ts']
  }
});

// vitest.setup.ts
import { expect, afterEach, vi } from 'vitest';
import { cleanup } from '@testing-library/react';

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

// Test helpers
export const mockApiResponse = (data: any, ok = true) => ({
  ok,
  json: () => Promise.resolve(data),
  body: new ReadableStream({ ... })
});
```

**Backend (Pytest):**
```python
# conftest.py
import pytest
from unittest.mock import MagicMock

@pytest.fixture
def mock_fastf1_session():
    """Fixture providing a mocked FastF1 session."""
    session = MagicMock()
    session.results = pd.DataFrame({
        'Position': [1, 2, 3],
        'Abbreviation': ['VER', 'LEC', 'SAI'],
        'Time': [pd.Timedelta(minutes=1, seconds=30),
                 pd.Timedelta(minutes=1, seconds=32),
                 pd.Timedelta(minutes=1, seconds=33)]
    })
    return session

@pytest.fixture
def mock_tavily_client(mocker):
    """Fixture providing a mocked Tavily search client."""
    client = MagicMock()
    client.search.return_value = {
        'results': [
            {'title': 'Test', 'content': 'Snippet', 'url': 'http://example.com'}
        ]
    }
    return client
```

---

*Testing analysis: 2026-02-16*
