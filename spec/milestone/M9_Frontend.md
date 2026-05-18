# M9: Frontend
Status: in progress

Wire the existing backend endpoints into a usable UI. All business logic stays in
the backend; the frontend calls existing API/HTML endpoints.

---

- [x] **1.** `refactor: add status and updated_at to ArticleListItem`
  Adds `status` and `updated_at` to the shared `ArticleListItem` TypedDict and
  imports `Comment`/`Vote` in the articles router. Prerequisite for commits 4 and 7.
  `superhero_project/routers/_utils.py superhero_project/routers/articles.py`

- [x] **2.** `feat(nav): add site-wide navigation links`
  Adds Search, Browse (tags), New Article, My Articles, and Mod Queue links to the
  base nav. New Article and My Articles are auth-gated; Mod Queue is mod/admin only.
  `superhero_project/templates/base.html superhero_project/static/css/main.css`

- [x] **3.** `feat(article): add edit, history, and submit-for-review actions`
  View endpoint passes `can_edit` and `is_author` flags. Article page gains Edit and
  History links (always visible) and a Submit for Review button (draft author only)
  that POSTs to `/moderation/{id}/submit` via fetch.
  `superhero_project/routers/articles.py superhero_project/templates/article.html superhero_project/static/css/main.css`

- [x] **4.** `feat(article): add vote bar and comments section`
  View endpoint loads and passes vote summary and comments. Article page renders
  upvote/downvote buttons and a comment list with add/edit/delete; thin JS calls
  the existing `/votes` and `/comments` endpoints.
  `superhero_project/routers/articles.py superhero_project/templates/article.html superhero_project/static/js/article.js superhero_project/static/css/main.css`

- [x] **5.** `chore(frontend): add tsc pre-commit hook`
  Adds `pkgs.typescript` to devenv so `tsc` is available in the shell. Registers a
  pre-commit hook that runs `tsc --noEmit` (full project, via `tsconfig.json`) whenever
  any `.ts` file is staged.
  `devenv.nix .pre-commit-config.yaml`

- [x] **6.** `feat(editor): add article create and edit pages`
  Adds `GET /articles/new` and `GET /articles/{id}/edit` endpoints serving an editor
  form. Type selector shows/hides per-type metadata fields; live Markdown preview
  calls `/articles/render` (wired via `preview.ts`); form submits JSON to the existing
  create/update endpoints and redirects to the article view on success. Adds
  `editor.ts` to the esbuild inputs. Includes HTML-view tests for both endpoints.
  `superhero_project/routers/articles.py superhero_project/templates/editor.html superhero_project/static/ts/editor.ts superhero_project/static/css/main.css devenv.nix scripts/build_js.sh tests/test_articles.py`

- [x] **7.** `feat(me): add my articles page`
  Adds `GET /me/articles` listing all of the current user's articles across all
  statuses with links to view and edit each one.
  `superhero_project/routers/community.py superhero_project/main.py superhero_project/templates/me/articles.html superhero_project/static/css/main.css`
