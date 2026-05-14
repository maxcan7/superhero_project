# M4: Moderation
Status: complete

Submission workflow, moderation queue, status transitions.

---

- [x] **1.** `feat: add moderation router with queue and status transitions`
  Queue listing (pending articles), approve/reject/request-changes endpoints; moderator role guard.
  `superhero_project/routers/moderation.py`

- [x] **2.** `feat: add moderation queue template`
  Moderator-facing queue view with inline action buttons.
  `superhero_project/templates/moderation/queue.html`
