# Idea: Request Changes — Revision Notes and Author Notification

The current "Request Changes" moderation action transitions an article
`pending → draft` but provides no revision note and gives the author no
indication that anything happened or why. This makes the flow incomplete:
the author re-opens the editor with no context and must guess what to fix.

Not worth building until after a full manual test cycle confirms the rest
of the moderation queue is stable.

---

## Current behaviour

1. Moderator clicks "Request Changes" in the queue.
2. Article status flips `pending → draft`; the article disappears from the queue.
3. Author sees no notification. Their draft page looks identical to before submission.

---

## Desired behaviour

1. Moderator fills a short revision note, then clicks "Request Changes."
2. Article status flips `pending → draft`; the note is persisted against the article.
3. Author visits their "My Articles" page or opens the editor and sees the note prominently — something like a callout: *"Changes requested: [note text]"*.
4. Author edits and re-submits. On re-submit the note is cleared and the article re-enters the queue.

---

## Schema changes

### Option A — column on `articles`

Add `moderator_note TEXT` to `articles`. Simple; only one note at a time (the
most recent). Cleared on re-submit (`status: draft → pending`), publish, or
reject.

**Trade-off:** loses history of previous notes if the article cycles through
the queue more than once. Acceptable for v1.

### Option B — `moderation_actions` table

```sql
moderation_actions (
  id, article_id, moderator_id, action,  -- 'approved' | 'rejected' | 'changes_requested'
  note TEXT,
  created_at
)
```

Full audit trail; notes survive re-submissions. More schema complexity.

**Recommendation: start with Option A; migrate to Option B if the moderation
history feature is ever prioritised.**

---

## UI changes

- **Moderation queue**: replace the "Request Changes" button with a small form
  — a `<textarea>` for the note and a submit button. Note is optional but
  encouraged.
- **Editor page** (`/articles/{id}/edit`): if `status == draft` and
  `moderator_note` is non-empty, render a callout block above the editor with
  the note text. Callout is dismissed (visually only) once the author re-submits.
- **My Articles page**: add a "Changes requested" state indicator for affected
  drafts, mirroring the callout text.

---

## Notification model

The implementation sequence is:

1. **Build M12 first** — in-app notification inbox (tasks 1–4): `notifications`
   table, nav unread count, bell icon, `/me/notifications` page. The
   editor/My Articles callout is a secondary surface for context when the author
   is already looking at the affected article.

2. **Then add email (M12 task 5)** — once the inbox is stable, layer on email
   delivery. Requires adding `user:email` to the GitHub OAuth scope, storing
   the email on `users`, and wiring a transactional send (Resend recommended)
   as a best-effort side-effect of notification creation. Users with no email
   on file receive in-app notification only.

See [M12](../milestone/M12_ModerationNotifications.md) for the full design.

---

## Out of scope

- Push notifications.
- Threaded moderator ↔ author discussion on an article.
- Moderator note on reject (separate concern; could share notification infrastructure).
