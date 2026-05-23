# Idea: Search and Discovery Improvements

The current search supports FTS on slug+content, tag ILIKE matching, and
JSONB metadata filters. Discovery beyond keyword search is thin: there are
no browse-by-type pages, no recently-published feed, and the tag index
(already built) is not surfaced in the main nav. This limits wiki-diving
for users who don't know what they're looking for.

---

## Current state

- `/articles/search` — FTS + tag match + metadata filters (type, status, powers,
  location_type, org_type)
- `/tags/` and `/tags/{tag}` — tag index and per-tag article list (M5)
- No browse-by-type pages
- No recently-published feed
- Search link in nav goes directly to the search form; no discovery entry points

---

## Proposed additions

### 1. Browse by type

A landing page per article type listing all published articles, alphabetically.
Practically, this is the existing search results view filtered by type with no
query — `_build_search_stmt(q=None, type_filter="profile", ...)`.

- Route: `/articles/browse/{type}` (e.g. `/articles/browse/profile`)
- Template: can reuse `search.html` with a heading like "All Profiles" and no
  search box, or add a minimal `browse.html`.
- Nav: add a "Browse" dropdown or submenu with links for each type.

**This is the highest-value addition.** Users commonly want to explore all
characters or all organisations without a specific search term.

### 2. Recently published feed

A short list of the N most recently published articles, shown on the home page
or a dedicated `/recent` route. Ordered by `published_at DESC`, limit 20.

No new query infrastructure needed — plain `select(Article).where(published).order_by(published_at.desc()).limit(20)`.

### 3. Tag index in nav

The tag index at `/tags/` already exists but is not linked from the main nav.
Add it. Low effort, meaningfully improves discovery.

### 4. Search results — type facet counts

Alongside search results, show counts per type:
*"Profiles (3) · Orgs (1) · Locations (2)"* with each acting as a quick filter.

Requires a secondary `GROUP BY article_type` query against the same filter
conditions (minus the type filter). More complex than the other items; lower
priority.

### 5. Search by author

Filter search results to articles by a specific contributor. Useful for
finding all of a collaborator's work or auditing a user's contributions.

- UI: add an `author` field to the search form (GitHub username or display name).
- Query: join `users` on `author_id`, filter by `github_username ILIKE` or
  `display_name ILIKE`. Can be combined with existing FTS and metadata filters.
- Alternatively, the existing contributor profile page
  (`/contributors/{username}`) already lists authored articles — linking to it
  more prominently may be sufficient before a dedicated search parameter is
  worth adding.

### 6. Search by date

Filter by publication date range. Useful for finding recent contributions or
articles tied to a specific period of activity.

- UI: `published_after` and `published_before` date inputs on the search form.
- Query: `Article.published_at >= published_after`,
  `Article.published_at <= published_before`. Straightforward column comparisons;
  no new infrastructure needed.
- A "sort by date" toggle on results (newest first vs. relevance) is a related
  and simpler win.

### 7. Metadata browse pages

Dedicated pages for high-value metadata dimensions:

- All profiles with a given power (`/browse/power/{power}`)
- All active orgs (`/browse/orgs?status=active`)
- All locations by type (`/browse/locations?location_type=city`)

These are thin wrappers over existing JSONB filter logic. Useful once content
volume grows; premature at low article counts.

---

## Priority order

1. Browse by type (nav + per-type pages)
2. Tag index in nav
3. Recently published feed
4. Search by author
5. Search by date / sort by date
6. Metadata browse pages
7. Search result type facets

Items 1–3 are small and should be done together as a single milestone task.
Items 4–5 are low-infrastructure additions worth bundling with a search polish
pass. Items 6–7 are deferred until content volume makes them worthwhile.

---

## Out of scope

- Elasticsearch or external search index.
- Saved searches or search history.
- Autocomplete / typeahead.
