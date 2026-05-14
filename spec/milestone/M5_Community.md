# M5: Community
Status: complete

Voting, comments, contributor profiles, tag browsing.

---

- [x] **1.** `feat: add voting and comments routers`
  Up/downvote endpoint; enforces one vote per user per article via UNIQUE constraint.
  Create, edit, delete comments; author-only edit/delete; timestamps.
  `superhero_project/routers/votes.py superhero_project/routers/comments.py`

- [x] **2.** `feat: add contributor profiles and tag browsing`
  Author profile listing published articles; tag index page with article counts.
  `superhero_project/routers/articles.py superhero_project/templates/`

- [x] **3.** `feat: add article edit history with diff view`
  Write article_history row on each edit; history page shows unified diffs between snapshots.
  `superhero_project/routers/articles.py superhero_project/templates/`
