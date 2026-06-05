# M13: Search & Discovery
Status: not started

Three incremental improvements to search and discovery that require no schema
changes: browse-by-type pages, an author filter, and date-range/sort controls.
Requires M6 (search infrastructure).

---

## Overview

The search form supports FTS, tag matching, and JSONB metadata filters, but
offers no way to browse all articles of a given type, no way to filter by
author, and no date controls. This milestone adds all three in separate,
independently mergeable commits.

Browse-by-type reuses `_build_search_stmt` with `q=None` and a fixed
`type_filter`, so no new query logic is needed — just a route, a template, and
a nav entry point. Author and date filters extend the existing
`_build_search_stmt` / `search_articles` / `search.html` stack in the same
pattern as the existing metadata filters.

---

## Tasks

- [ ] **1.** `feat: add browse-by-type pages`
  New route `GET /articles/browse` renders a landing page listing all article
  types as links. New route `GET /articles/browse/{type}` calls
  `_build_search_stmt(q=None, type_filter=type, ...)` and renders an
  alphabetical article list with a heading like "All Profiles". Both routes use
  a new `browse.html` template (no search sidebar). Invalid or unknown type
  values return 404. Nav "Browse" link changes from `/tags` to
  `/articles/browse`; the browse landing page includes a "Browse by tag" link
  back to `/tags`.
  `superhero_project/routers/articles_html.py superhero_project/templates/browse.html superhero_project/templates/base.html`

- [ ] **2.** `feat: add author filter to article search`
  Add `author: str | None` query param to `search_articles`. Extend
  `_build_search_stmt` to accept `author`; when set, join `User` on
  `Article.author_id` and filter by `User.github_username.ilike(f"%{author}%")`.
  Add `author` to `_FILTER_CTX_DEFAULTS`. Add an author text input to
  `search.html` and update the "Clear filters" condition to include `author`.
  `superhero_project/routers/articles_html.py superhero_project/templates/search.html`

- [ ] **3.** `feat: add date range and sort controls to article search`
  Add `published_after: date | None`, `published_before: date | None`, and
  `sort: str | None` query params to `search_articles`. Extend
  `_build_search_stmt` to filter `Article.published_at >= published_after` and
  `Article.published_at <= published_before` when set; `sort="date"` overrides
  the default FTS-rank ordering with `Article.published_at.desc()`. Add all
  three to `_FILTER_CTX_DEFAULTS`. Add date inputs and a sort select to
  `search.html`; update the "Clear filters" condition.
  `superhero_project/routers/articles_html.py superhero_project/templates/search.html`

---

## Design decisions

- **Separate `browse.html`**: the browse view has no search sidebar, so a
  dedicated template is cleaner than adding a mode flag to `search.html`.
- **Author filter by ILIKE**: partial match on `github_username` is the
  simplest useful behaviour; display name is not searched to avoid the extra
  join complexity and because GitHub username is the canonical identity here.
- **`sort` as freeform string**: accepts `"date"`, treats anything else (or
  `None`) as relevance order. Avoids a `Literal` import or enum for a
  two-value toggle.

---

## Deferred

**Search result type facet counts** — alongside results, show per-type counts
acting as quick filters: *"Profiles (3) · Orgs (1) · Locations (2)"*. Requires
a secondary `GROUP BY article_type` query against the same filter conditions
minus the type filter. More complex than the other items; deferred until the
results page feels crowded without it.

**Metadata browse pages** — dedicated pages for high-value metadata dimensions:
all profiles with a given power (`/browse/power/{power}`), all active orgs
(`/browse/orgs?status=active`), all locations by type
(`/browse/locations?location_type=city`). Thin wrappers over existing JSONB
filter logic; premature at current content volume.

---

## Out of scope

- Elasticsearch or external search index.
- Saved searches or search history.
- Autocomplete / typeahead.
- **Type facet counts and metadata browse pages** are deferred (see below).
