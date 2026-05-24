# C6: Replace slug/designation with user-defined page_name
Status: in-progress

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

- [x] **1.** `refactor(db): rename slug→page_name, drop designation`
  Alembic migration using `op.alter_column` / `op.drop_column`:
  ```sql
  ALTER TABLE articles RENAME COLUMN slug TO page_name;
  ALTER TABLE articles DROP COLUMN designation;
  ```
  Update `db/models.py`: rename the `slug` mapped column to `page_name`; remove the
  `designation` mapped column.
  `superhero_project/db/models.py alembic/versions/4fe5c7b33599_rename_slug_to_page_name.py`

- [x] **2.** `refactor(domain): rename slug→page_name, remove designation indexing`
  In `domain/links.py`:
  - Renamed `SlugMap` → `PageNameMap` type alias; also renamed the `slug_map` local
    variable to `page_name_map` throughout (not left in place as originally planned).
  - Remove `index_designation: bool` from `TypeHandler` and its only use
    (`ArticleType.profile` handler, `index_designation=True`).
  - Remove the `if handler.index_designation` branch in `build_alias_index`.
  - Update raw SQL queries to select `a.page_name` only; remove `"designation"` from
    result dicts.
  In `domain/infobox.py` (not originally listed here):
  - Rename `slug` → `page_name` in `ResolvedLink` TypedDict and `_field_edge_map`.
  `superhero_project/domain/links.py superhero_project/domain/infobox.py`

- [x] **3.** `refactor(routers): rename slug→page_name, remove designation, remove profile special-case`
  In `routers/_utils.py`:
  - Remove `_CAPE_RE` and the designation-vs-slug branching in `fetch_article`; always look up by `Article.page_name`.
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
  - Rename `slug` → `page_name` and remove `designation` from any response schemas or dict literals.

  In `routers/articles_html.py`:
  - Replace every `article.designation or article.slug` with `article.page_name`.
  - Replace `"identifier": article.designation or article.slug` with
    `"identifier": article.page_name`.
  `superhero_project/routers/_utils.py superhero_project/routers/articles.py superhero_project/routers/moderation.py superhero_project/routers/articles_html.py`

- [x] **4.** `refactor(templates): rename Slug→Page name, show for all types`
  In `templates/editor.html`:
  - Change `id="slug-group"` → `id="page-name-group"`.
  - Change label text from `Slug` to `Page name`.
  - Change `id="article-slug"` → `id="article-page-name"`.
  - Update placeholder to `url-friendly-name` and hint to
    `Unique name for this article's URL, e.g. <code>ms-marvel</code>.`

  All other templates that used `article.designation or article.slug` (not just via
  router context) were also updated directly to `article.page_name`.
  `superhero_project/templates/editor.html superhero_project/templates/`

- [x] **5.** `refactor(ts): show page-name field for all article types`
  In `static/ts/editor.ts`:
  - Remove `slugGroup.hidden = type === 'profile'` — the field is shown whenever any
    type is selected.
  - Rename element ID references: `slug-group` → `page-name-group`,
    `article-slug` → `article-page-name`.
  - Rename the field key sent in the POST body from `slug` to `page_name`.
  `noEmit: true` in tsconfig means `tsc` does not produce `.js` output; `editor.js` was manually kept in sync with the TypeScript changes (not compiled).
  `superhero_project/static/ts/editor.ts`

- [x] **6.** `refactor(tests): update fixtures and article tests for page_name`
  In `tests/conftest.py`:
  - Remove all `designation=` kwargs from `Article(...)` construction.
  - Rename `slug=` → `page_name=` in `Article(...)` construction.

  In `tests/utils.py`:
  - Remove `designation` parameter from `make_article`; rename `slug` → `page_name`.
  - Update `WIKILINK_EDGE` and `GOTHAM_EDGE` dict keys from `"slug"` to `"page_name"`.

  In `tests/test_articles.py`:
  - Delete `test_create_profile_auto_assigns_designation`; replace with
    `test_create_profile_with_explicit_page_name`.
  - Rename all `data["slug"]` → `data["page_name"]`; remove any `data["designation"]` assertions.

  In `tests/test_links.py`:
  - Remove `designation` from parametrize table and `build_alias_index` call; rename
    `slug` → `page_name`.

  Also updated (not in original spec):
  - `tests/test_votes.py`: renamed `published_article.slug` → `.page_name`.
  - `tests/test_infobox.py`: updated `_AVENGERS_EDGE` dict key and `ResolvedLink`
    constructor kwargs.

  All other test files that referenced `.slug` on fixture articles were updated to
  `.page_name`.
  `tests/`

- [ ] **7.** `refactor(scripts): update seed and smoke for page_name`
  In `scripts/dev_seeds/seed_rebis.py`:
  - Replace `_insert_profile` (which auto-generated the CAPE slug) with a call to the unified `_insert_article`, passing an explicit `page_name`; removed `import uuid`.
  - Rename `slug` → `page_name` in all article dicts and helper signatures.
  - Remove `profile_slugs` dict and its print block.

  In `scripts/smoke.py`:
  - Add `"page_name": "smoke-profile"` to the profile creation payload.
  - Rename `slug` → `page_name` in all references.
  `scripts/dev_seeds/seed_rebis.py scripts/smoke.py`
