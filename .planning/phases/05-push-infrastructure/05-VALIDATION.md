---
phase: 5
slug: push-infrastructure
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-05-01
---

# Phase 5 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x |
| **Config file** | none — Wave 0 installs |
| **Quick run command** | `cd backend && python -m pytest tests/push/ -x -q` |
| **Full suite command** | `cd backend && python -m pytest tests/ -q` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `cd backend && python -m pytest tests/push/ -x -q`
- **After every plan wave:** Run `cd backend && python -m pytest tests/ -q`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 20 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 05-W0-01 | W0 | 0 | PUSH-01 | — | N/A | unit stub | `python -m pytest tests/push/test_register.py -x -q` | ❌ W0 | ⬜ pending |
| 05-W0-02 | W0 | 0 | PUSH-02 | — | N/A | unit stub | `python -m pytest tests/push/test_dispatch.py -x -q` | ❌ W0 | ⬜ pending |
| 05-W0-03 | W0 | 0 | PUSH-03 | — | N/A | unit stub | `python -m pytest tests/push/test_token_mgmt.py -x -q` | ❌ W0 | ⬜ pending |
| 05-01-01 | 01 | 1 | PUSH-01 | — | Token upsert never duplicates rows | unit | `python -m pytest tests/push/test_register.py -x -q` | ❌ W0 | ⬜ pending |
| 05-01-02 | 01 | 1 | PUSH-01 | — | 410 Unregistered triggers immediate row delete | unit | `python -m pytest tests/push/test_register.py::test_410_cleanup -x -q` | ❌ W0 | ⬜ pending |
| 05-02-01 | 02 | 2 | PUSH-02 | — | push.register endpoint returns 200 + stored token | integration | `python -m pytest tests/push/test_register.py::test_register_endpoint -x -q` | ❌ W0 | ⬜ pending |
| 05-02-02 | 02 | 2 | PUSH-02 | — | Preferences filter blocks unwanted event types | unit | `python -m pytest tests/push/test_dispatch.py::test_preference_filter -x -q` | ❌ W0 | ⬜ pending |
| 05-03-01 | 03 | 3 | PUSH-03 | — | aioapns singleton initializes from env cert | unit | `python -m pytest tests/push/test_dispatch.py::test_apns_client_init -x -q` | ❌ W0 | ⬜ pending |
| 05-03-02 | 03 | 3 | PUSH-02 | — | Dispatch sends correct APNs payload structure | unit | `python -m pytest tests/push/test_dispatch.py::test_payload_structure -x -q` | ❌ W0 | ⬜ pending |
| 05-04-01 | 04 | 4 | PUSH-04 | — | physical device receives notification (manual) | manual | see Manual-Only section | N/A | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `backend/tests/push/__init__.py` — test package init
- [ ] `backend/tests/push/test_register.py` — stubs for PUSH-01, PUSH-03
- [ ] `backend/tests/push/test_dispatch.py` — stubs for PUSH-02
- [ ] `backend/tests/push/test_token_mgmt.py` — stubs for PUSH-03 token cleanup
- [ ] `backend/tests/conftest.py` — shared fixtures (async DB session, mock aioapns client)
- [ ] `pytest`, `pytest-asyncio`, `httpx`, `aiosqlite` install — test dependencies

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Physical iOS device receives push notification | PUSH-04 | Requires real APNs sandbox + physical device; cannot simulate in CI | 1. Deploy backend to Render staging with APNS_CERT_BASE64 set. 2. Build iOS app with sandbox entitlements. 3. Launch live session via test endpoint. 4. Verify notification appears on lock screen within 5 seconds of event. |
| Notification deep-links to live timing tab | PUSH-04 | Requires human observation of app navigation | Tap received notification; verify app opens to Live Timing tab. |
| Sandbox vs. production APNs endpoint selection | PUSH-04 | Requires both environments to fully test | Set ENVIRONMENT=dev → confirm sandbox.push.apple.com used; set ENVIRONMENT=prod → confirm push.apple.com used. |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 20s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
