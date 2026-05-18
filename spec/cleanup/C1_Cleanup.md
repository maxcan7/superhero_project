# C1: Code Cleanup
Status: complete

Semantic cleanup, separation of responsibilities, and deduplication across routers. No new features or schema changes.

---

## Group A — Centralize shared constants and utilities

- [x] **1.** `refactor: centralize CAPE regex and fetch_article in _utils`
  Remove the duplicate `_CAPE_RE` compilations in `articles.py` and `moderation.py`; both already import from `_utils.py` where the canonical copy lives. Same for `_fetch()` — replace the local copies with `fetch_article()` from `_utils`.
  `superhero_project/routers/articles.py superhero_project/routers/moderation.py superhero_project/routers/_utils.py`

- [x] **2.** `refactor: move article list-item serialization to _utils`
  `community.py` has `_list_item(article)` that builds the dict `{slug, designation, article_type, metadata, tags}`; `main.py` inlines the same shape. Extract to `_utils.py` and replace both callsites.
  `superhero_project/routers/community.py superhero_project/routers/_utils.py superhero_project/main.py`

---

## Group B — Separate dual-workflow views

- [x] **3.** `refactor: split profile creation out of create_article`
  `create_article()` branches on `is_profile` to use a temp UUID slug, flush early, and derive the CAPE designation — a second workflow hidden inside a generic handler. Extract to `_create_profile()`, leaving `create_article()` with only the straight-line path.
  `superhero_project/routers/articles.py`

- [x] **4.** `refactor: split search form and results into explicit template contexts`
  `search.html` uses `{% if q %}` to toggle between two views, mirroring the original pre-split state. The routes `search_form` and `search_articles` are already split; pass an explicit `results` key (list or `None`) from each and remove the `if q` conditional from the template.
  `superhero_project/routers/articles.py superhero_project/templates/search.html`

- [x] **5.** `refactor: separate author-submit and moderator-submit in moderation router`
  `submit_article()` silently allows either the article's own author or a moderator to call it, with two different permission semantics. Split into `submit_own_article()` (author-only guard) and a moderator-facing submit path, or at minimum make the two authorization branches explicit named helpers rather than an inline `if`.
  `superhero_project/routers/moderation.py`

---

## Group C — Extract repeated authorization checks

- [x] **6.** `refactor: extract comment ownership guard into helper`
  `update_comment()` and `delete_comment()` both inline `if user.id != comment.author_id` with identical error handling. Extract to `_require_comment_author(user, comment)` matching the pattern of `_require_moderator`.
  `superhero_project/routers/comments.py`

---

## Group D — Separate data access from business logic

- [x] **7.** `refactor: split _build_history into fetch and diff steps`
  `_build_history()` loads history records from the DB and computes diffs in the same function. Split into `_load_history(article, db)` (query only) and `_compute_diffs(records)` (pure logic), then call them in sequence at the two callsites.
  `superhero_project/routers/articles.py`

- [x] **8.** `refactor: extract vote upsert logic out of cast_vote handler`
  The check-then-insert-or-update pattern in `cast_vote()` lives directly in the HTTP handler. Extract to `_upsert_vote(user_id, article_id, value, db)` so the handler owns only request/response concerns.
  `superhero_project/routers/votes.py`

---

## Group E — Clarify intent at mutation sites

- [x] **9.** `refactor: make tag replacement explicit in update_article`
  `article.tags = [ArticleTag(...) for tag in body.tags]` reads as assignment but relies on ORM cascade to delete old tags. Replace with an explicit delete-then-insert sequence so the intent is visible without knowing the relationship config.
  `superhero_project/routers/articles.py`
