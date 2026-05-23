# C6: Replace slug/designation with user-defined page_name
Status: pending

The `slug` column conflates two distinct concerns: an internal record identifier and a user-visible URL name. The `designation` column (`CAPE-{id}`) was a second internal identifier, redundant with the integer primary key. Profile articles were further special-cased to auto-generate their slug from the designation, hiding the field entirely in the editor and routing through a separate code path.

This cleanup collapses all of that:

- **Drop `designation`** — the integer `id` is the authoritative internal key.
- **Rename `slug` → `page_name`** throughout (DB, model, schemas, API JSON, domain,
  templates, tests, scripts).
- **Remove profile auto-generation** — all article types require an explicit `page_name`
  on creation; no type is special-cased.
- **Editor label** changes from "Slug" to "Page name"; the field is shown for all types.

---

## Tasks

- [ ] **1.** `refactor(db): rename slug→page_name, drop designation`
  Alembic migration:
  ```sql
  ALTER TABLE articles RENAME COLUMN slug TO page_name;
  ALTER TABLE articles DROP COLUMN designation;
  ```
  Update `db/models.py`: rename the `slug` mapped column to `page_name`; remove the
  `designation` mapped column.
  `superhero_project/db/models.py alembic/versions/<hash>_rename_slug_to_page_name.py`

- [ ] **2.** `refactor(domain): rename slug→page_name, remove designation indexing`
  In `domain/links.py`:
  - Rename `SlugMap` type alias comment (`article_id → page_name`); the variable name
    `slug_map` may stay for now but the raw SQL queries must reference `page_name`.
  - Remove `index_designation: bool` from `TypeHandler` and its only use
    (`ArticleType.profile` handler, `index_designation=True`).
  - Remove the `if handler.index_designation` branch in `build_alias_index` and
    `_collect_aliases`.
  - Update the two raw SQL queries that select `a.slug, a.designation` to select
    `a.page_name` only; remove `"designation"` from result dicts.
  `superhero_project/domain/links.py`

- [ ] **3.** `refactor(routers): rename slug→page_name, remove designation, remove profile special-case`
  In `routers/_utils.py`:
  - Remove `_CAPE_RE` and the designation-vs-slug branching in `fetch_article`; always
    look up by `Article.page_name`.
  - Rename `slug` → `page_name` in `ArticleListItem` and `article_list_item`.
  - Remove `designation` from `ArticleListItem` and `article_list_item`.

  In `routers/articles.py`:
  - Delete `_create_profile`; remove the `if body.article_type == ArticleType.profile`
    branch that called it.
  - Rename `slug` → `page_name` in `ArticleCreate` (remove the default `= ""`; field is
    required) and `ArticleOut`.
  - Remove `designation` from `ArticleOut`.
  - Remove `uuid` import (no longer needed).
  - Update `_to_out` and the unified `create_article` path to use `page_name`.
  - Update module docstring.

  In `routers/moderation.py`:
  - Rename `slug` → `page_name` and remove `designation` from any response schemas or
    dict literals.

  In `routers/articles_html.py`:
  - Replace every `article.designation or article.slug` with `article.page_name`.
  - Replace `"identifier": article.designation or article.slug` with
    `"identifier": article.page_name`.
  `superhero_project/routers/_utils.py superhero_project/routers/articles.py superhero_project/routers/moderation.py superhero_project/routers/articles_html.py`

- [ ] **4.** `refactor(templates): rename Slug→Page name, show for all types`
  In `templates/editor.html`:
  - Change `id="slug-group"` → `id="page-name-group"`.
  - Change label text from `Slug` to `Page name`.
  - Change `id="article-slug"` → `id="article-page-name"`.
  - Update placeholder to `url-friendly-name` and hint to
    `Unique name for this article's URL, e.g. <code>ms-marvel</code>.`

  All other templates use `article.designation or article.slug` only via the router
  context variable `identifier`; those are handled in task 3. Any remaining direct
  `article.slug` references must be updated to `article.page_name`.
  `superhero_project/templates/editor.html superhero_project/templates/`

- [ ] **5.** `refactor(ts): show page-name field for all article types`
  In `static/ts/editor.ts`:
  - Remove `slugGroup.hidden = type === 'profile'` — the field is shown whenever any
    type is selected.
  - Rename element ID references: `slug-group` → `page-name-group`,
    `article-slug` → `article-page-name`.
  - Rename the field key sent in the POST body from `slug` to `page_name`.
  Recompile: `tsc --project tsconfig.json`.
  `superhero_project/static/ts/editor.ts superhero_project/static/js/editor.js`

- [ ] **6.** `refactor(tests): update fixtures and article tests for page_name`
  In `tests/conftest.py`:
  - Remove all `designation=` kwargs from `Article(...)` construction.
  - Rename `slug=` → `page_name=` in `Article(...)` construction.

  In `tests/utils.py`:
  - Remove `designation` parameter from `make_article`; rename `slug` → `page_name`.

  In `tests/test_articles.py`:
  - Delete `test_create_profile_auto_assigns_designation`; replace with a test that
    creates a profile with an explicit `page_name` and asserts the API returns it.
  - Rename all `data["slug"]` → `data["page_name"]`; remove any `data["designation"]`
    assertions.

  In `tests/test_links.py`:
  - Remove `designation` from parametrize table and `build_alias_index` call; rename
    `slug` → `page_name`.

  All other test files that reference `.slug` on a fixture article must be updated to
  `.page_name`.
  `tests/conftest.py tests/utils.py tests/test_articles.py tests/test_links.py tests/test_moderation.py tests/test_community.py tests/test_articles_html.py`

- [ ] **7.** `refactor(scripts): update seed and smoke for page_name`
  In `scripts/dev_seeds/seed_rebis.py`:
  - Replace `_insert_profile` (which auto-generated the CAPE slug) with a call to the
    unified insert helper, passing an explicit `page_name` derived from the profile's
    primary alias (e.g. `rebis-bondi`).
  - Rename `slug=` → `page_name=` in all article dicts and helper signatures.
  - Remove `profile_slugs` dict and its print block; profiles are no longer identified
    by a separate designation.

  In `scripts/smoke.py`:
  - Add `"page_name": "smoke-profile"` (or similar) to the profile creation payload.
  - Rename `slug` → `page_name` in all references.
  `scripts/dev_seeds/seed_rebis.py scripts/smoke.py`

- [ ] **8.** `docs: update M3 and C4 for page_name`
  In `spec/milestone/M3_Articles.md`: update task 2 description to replace
  "designation routing for profiles, slug routing for all others" with
  "page_name routing for all types".
  In `spec/cleanup/C4_ComicType.md`: update "Slug convention" note to "Page name
  convention: same for all types".
  `spec/milestone/M3_Articles.md spec/cleanup/C4_ComicType.md`
