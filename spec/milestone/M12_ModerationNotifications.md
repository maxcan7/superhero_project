# M12: Moderation Notifications
Status: in-progress

Completes the "Request Changes" moderation flow with revision notes and an
in-app notification inbox, with optional email delivery as a follow-on task.
Requires M4 (moderation queue) and M9 (nav/frontend).

---

## Overview

The current "Request Changes" action silently flips an article `pending → draft`
with no note and no signal to the author. This milestone fixes that in two layers:

1. **Revision notes** — moderator attaches a short note when requesting changes;
   it appears as a callout on the editor and My Articles pages.

2. **Notification inbox** — a `notifications` table and nav-level unread count
   so authors are alerted on their next page load, not just when they happen to
   open the editor.

The notification infrastructure is generic enough to support future event types
(e.g. comment replies, article approved) without further schema changes.

```
Moderator queue                    Author
─────────────────                  ──────────────────────────────────
[Request Changes]           →      nav: 🔔 1 unread
  + note textarea                  /me/notifications: "Changes requested on CAPE-0042: ..."
                                   /articles/CAPE-0042/edit: callout with note text
```

---

## Schema

### Migration 1 — `moderator_note` on `articles`

```sql
ALTER TABLE articles ADD COLUMN moderator_note TEXT;
```

Nullable. Set when a moderator requests changes. Cleared (set to NULL) when
the author re-submits (`draft → pending`), or when the article is published
or rejected.

### Migration 2 — `notifications` table

```sql
notifications (
  id          BIGSERIAL PRIMARY KEY,
  user_id     BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  type        TEXT NOT NULL,           -- 'changes_requested' | extensible
  article_id  BIGINT REFERENCES articles(id) ON DELETE CASCADE,
  message     TEXT NOT NULL,
  read        BOOLEAN NOT NULL DEFAULT false,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
)
```

---

## Tasks

- [x] **1.** `feat: add moderator_note column and notifications table`
  Two Alembic migrations (keep them separate so each is independently
  revertible). `moderator_note TEXT` on `articles`; full `notifications` table
  as above. Add `Notification` ORM model.
  `alembic/versions/ superhero_project/db/models.py`

- [x] **2.** `feat: add revision note to request-changes moderation action`
  Replace the "Request Changes" button in the queue with a small inline form:
  `<textarea>` (optional) + submit button. The POST endpoint
  (`/moderation/{id}/request-changes`) accepts `note: str | None`, writes it to
  `articles.moderator_note`, and creates a `notifications` row for the author
  with `type='changes_requested'` and a message derived from the note.
  `superhero_project/routers/moderation.py superhero_project/templates/moderation/`

- [ ] **3.** `feat: show revision note callout on editor and My Articles`
  On the editor page, if `article.moderator_note` is non-empty, render a
  callout above the form: *"Changes requested: [note]"*. Same indicator on the
  My Articles page for affected drafts. On re-submit, the router clears
  `moderator_note` and sets `status = pending`.
  `superhero_project/routers/articles_html.py superhero_project/templates/`

- [ ] **4.** `feat: notification inbox and nav unread count`
  New route `/me/notifications` listing the authenticated user's notifications,
  newest first, with mark-as-read on visit. Nav bar gains a bell icon with an
  unread count badge (hidden when zero), populated by a count query injected
  into base template context via a middleware or base context helper.
  `superhero_project/routers/community.py superhero_project/templates/`

- [ ] **5. (optional)** `feat: email delivery for notifications`
  Send an email when a notification is created, if the user has an email address
  on file. Requires two prerequisites not yet in the stack:

  - **OAuth scope**: add `user:email` to the GitHub OAuth request and store the
    returned primary email in a new `users.email` column (nullable — GitHub
    users may have no public email). Users with no email on file receive
    in-app notification only.
  - **Sending service**: use a transactional email provider (Resend recommended
    — HTTP API, generous free tier). API key stored as an environment variable
    alongside `SESSION_SECRET`. Send is a best-effort fire-and-forget; failure
    must not break the notification creation transaction.

  `alembic/versions/ superhero_project/db/models.py superhero_project/routers/auth.py superhero_project/domain/notifications.py`

---

## Design decisions

- **One note at a time**: `moderator_note` on `articles` (Option A from the
  idea spec) is sufficient for v1. If moderation history is ever prioritised,
  migrate to a `moderation_actions` audit table at that point.
- **Notification fan-out**: only the article author is notified on
  "Request Changes". The `type` column keeps future event types additive.
- **Mark-as-read**: visiting `/me/notifications` marks all as read (bulk).
  Per-item read state is stored but a per-item dismiss UI is not required for v1.
- **Email is additive**: tasks 1–4 are the complete deliverable. Task 5 layers
  email on top without touching any prior task's code — it only adds the OAuth
  scope change, the email column, and a post-commit send in the notification
  creation path.
