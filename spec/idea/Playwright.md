# Idea: Playwright Browser Tests

End-to-end browser tests that drive a real browser session, covering flows that
require the full GitHub OAuth round-trip or depend on browser-level behaviour
(redirects, cookie state, rendered UI).

Not worth implementing until the OAuth app is stable and the UI is settled.
Playwright tests are slower and more brittle than the smoke script; keep the
smoke script as the primary live-server check.

---

## Prerequisites

- A dedicated test GitHub account (separate from the dev account used for manual
  testing) with the OAuth app pre-authorized.
- `PLAYWRIGHT_GITHUB_USER` and `PLAYWRIGHT_GITHUB_PASS` in `.env.playwright`
  (never committed).
- `pytest-playwright` added to the `dev` dependency group in `pyproject.toml`, then `uv sync && playwright install chromium`

---

## Proposed test flows

### Authentication
- Full login: home → click Sign In → GitHub consent page → authorize → land back
  as logged-in user; session cookie present.
- Session persists across page navigation (reload stays logged in).
- Logout: click Sign Out → cookie cleared → home page shows Sign In again.
- Direct navigation to `/moderation/queue` while logged out → redirected to home
  (or login prompt).

### Role-based UI
- Contributor: Submit button visible on own draft; approve/reject buttons absent.
- Moderator: moderation queue link visible in nav; approve/reject buttons present.
- Anon: no edit/submit/vote controls visible on article pages.

### Article authoring
- Create a profile article via the form; verify it appears in the contributor's
  draft list.
- Edit the article; verify a history entry appears on the history page.
- Submit for review; verify status changes to pending and the article appears in
  the moderation queue.

### Moderation
- Log in as moderator; approve the pending article; verify it appears on the home
  page and is searchable.
- Reject an article; verify it returns to draft status.

### Engagement
- Vote +1 on a published article; verify score increments.
- Post a comment; verify it appears without reload.
- Edit and delete own comment; verify UI updates correctly.
