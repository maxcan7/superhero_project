# C3: Split articles.py into API and HTML view modules
Status: not started

`articles.py` has grown to ~490 lines covering three distinct concerns: a JSON
API, HTML template views, and shared helpers/models used by both. The HTML view
handlers are the natural split point — they have different dependencies (template
context loaders, Jinja2) and a different call shape than the API handlers.

Split into two router modules that share helpers via import.

---

- [x] **1.** `refactor(articles): extract HTML views to articles_html.py`
  Create `superhero_project/routers/articles_html.py` with its own
  `APIRouter(prefix="/articles")`. Move the six HTML endpoints into it:
  `new_article_form`, `search_form`, `search_articles`, `view_article_html`,
  `view_article_history`, and `edit_article_form`. Move the two HTML-only context
  loaders (`_load_vote_context`, `_load_comments`) with them. All other helpers
  and models (`_render`, `_can_edit`, `_to_out`, `_content_diff`, `_load_history`,
  `_compute_diffs`, `ArticleOut`, `HistoryEntryOut`, etc.) stay in `articles.py`
  and are imported by `articles_html.py`.

  Register `articles_html.router` in `main.py` **before** `articles.router` —
  required so that fixed paths (`/new`, `/search`) match before the parametric
  `/{identifier}` catch-all.

  No behaviour change; all existing tests pass unchanged.
  `superhero_project/routers/articles.py superhero_project/routers/articles_html.py superhero_project/main.py`
