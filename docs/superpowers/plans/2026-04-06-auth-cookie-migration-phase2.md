# Auth Cookie Migration Phase 2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move browser auth from readable token storage to httpOnly cookies while keeping the current login flow working for operators.

**Architecture:** The backend will set and clear an auth cookie and accept JWTs from either the Authorization header or the cookie. The frontend will stop persisting JWTs entirely, switch authenticated requests to `credentials: 'include'`, and bootstrap auth state from a lightweight session endpoint instead of browser storage.

**Tech Stack:** FastAPI, jose JWT, React, TypeScript, Jest, pytest

---

### Task 1: Define cookie-backed auth behavior with tests

**Files:**
- Modify: `backend/app/tests/test_auth_api.py`
- Modify: `frontend/src/lib/api.test.ts`
- Modify: `frontend/src/App.test.tsx`

- [ ] Add backend tests for login cookie, session probe, and logout cookie clearing.
- [ ] Add frontend tests proving login no longer writes JWTs into storage and that auth rehydration uses `/api/auth/session`.
- [ ] Run the focused tests and confirm they fail for the expected reason before changing production code.

### Task 2: Add secure cookie auth support on the backend

**Files:**
- Modify: `backend/app/api/auth.py`
- Modify: `backend/app/api/deps.py`
- Modify: `backend/app/schemas/token.py`

- [ ] Set the JWT as an httpOnly cookie on successful login.
- [ ] Add session and logout endpoints that work with the cookie.
- [ ] Update auth dependency code so protected endpoints accept either bearer header or auth cookie during the migration.
- [ ] Keep cookie flags environment-aware so local HTTP still works and production can use `Secure`.

### Task 3: Switch the frontend to cookie-based session state

**Files:**
- Modify: `frontend/src/lib/api.ts`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/features/media/api.test.ts`

- [ ] Remove JWT persistence logic from browser storage.
- [ ] Make login/logout/session checks use `credentials: 'include'`.
- [ ] Make authenticated fetches rely on browser cookies instead of attaching Authorization headers.
- [ ] Keep UI login state working after reload via session bootstrap.

### Task 4: Align docs and verify the migration

**Files:**
- Modify: `ARCHITECTURE.md`

- [ ] Update the security doc section to reflect cookie-based auth.
- [ ] Run targeted backend and frontend validation.
- [ ] Summarize residual risks, especially CSRF and any remaining header-token compatibility.
