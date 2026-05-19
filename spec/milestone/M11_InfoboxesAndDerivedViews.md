# M11: Infoboxes & Derived Views
Status: completed

Structured rendering of domain metadata as visual infoboxes, plus derived aggregation views generated entirely from the link graph. Requires M10.

---

## Overview

M10 established the edge table. M11 is the surface area that makes it visible and useful. Two distinct concerns:

1. **Infoboxes** — the JSONB metadata that currently renders as a raw sidebar gets replaced with per-type template fragments. Fields become visual elements: status chips, linked lists, text badges.

2. **Derived views** — pages and sections that aggregate relationship data from `article_links` without any author input. An org's member roster, a location's event history, and so on — all generated from the edges M10 writes.

```
  metadata_ (JSONB)                     article_links
       │                                      │
       ▼                                      ▼
  ┌──────────────────────┐       ┌─────────────────────────────┐
  │  Per-type infobox    │       │  Derived views              │
  │                      │       │                             │
  │  Profile:            │       │  Org → member roster        │
  │    powers [badges]   │       │  Location → events here     │
  │    status [chip]     │       │  Location → residents       │
  │    affiliation [↗]   │       │                             │
  │                      │       │  Search filters             │
  │  Event:              │       │  ?status=active             │
  │    participants [↗]  │       │  ?powers=flight             │
  │    location [↗]      │       │  ?org_type=team             │
  └──────────────────────┘       └─────────────────────────────┘
```

---

## Tasks

- [x] **1.** `feat: add per-type infobox template fragments`
  One Jinja2 fragment per article type under `templates/infobox/`. The article template includes the appropriate fragment based on `article.article_type`. Fields are rendered as specific UI elements rather than raw key/value pairs.

  Rendering rules per type:

  ```
  Profile:
    aliases            → text badges (these are the article's own names, not links)
    affiliation        → linked list (via article_links; plain text if unresolved)
    powers             → text badges
    status             → colored chip
                         active=green, retired=yellow, deceased=red, unknown=grey
    base_of_operations → hyperlink if resolvable, plain text otherwise
    first_appearance   → plain text

  Location:
    location_type      → chip
    region             → plain text
    status             → colored chip (active, destroyed=red, abandoned=yellow)
    notable_residents  → linked list

  Event:
    event_date         → plain text
    location           → hyperlink if resolvable
    participants       → linked list
    outcome            → plain text

  Org:
    org_type           → chip
    aliases            → text badges
    founded            → plain text
    headquarters       → hyperlink if resolvable
    status             → colored chip
    affiliation        → linked list

  Tech:
    tech_type          → chip
    origin             → plain text
    current_holder     → hyperlink if resolvable
    status             → colored chip (active, destroyed=red, lost=yellow)

  Lore:
    category           → chip
    related_articles   → linked list

  Comic:
    comic_type         → chip
    publishers         → linked list (via article_links; plain text if unresolved)
    first_issue        → plain text
    last_issue         → plain text
    status             → colored chip: ongoing=green, completed=grey, cancelled=red, unknown=grey

  Disambiguation:
    (no infobox — DisambiguationMetadata has no fields; the article template
    skips the infobox fragment entirely for this type)
  ```

  "Linked list" means: for resolved values, use the pre-resolved edges from `article_links` to get the target slug and render as `<a href>`; for values that did not resolve at save time, fall back to the raw metadata string as plain text. Fields with no value set render as "—" or are omitted entirely.
  `superhero_project/templates/infobox/ superhero_project/templates/article.html superhero_project/static/css/`

- [x] **2.** `feat: add org member roster derived view`
  Standalone route at `/articles/{slug}/members` listing all published profiles whose `affiliation` edge points to this org. Linked from the org article page with a "View all members →" link.

  Query:
  ```sql
  SELECT a.slug, a.designation, a.metadata_->>'status' as status
  FROM article_links al JOIN articles a ON a.id = al.source_id
  WHERE al.target_id = :org_id
    AND al.field_name = 'affiliation'
    AND a.article_type = 'profile'
    AND a.status = 'published'
  ORDER BY a.metadata_->>'status', a.slug;
  ```

  Display: grouped by profile status (active first), each entry showing designation + aliases chip row. Standalone page allows pagination if the roster grows.
  `superhero_project/routers/articles_html.py superhero_project/templates/`

- [x] **3.** `feat: add location activity derived view`
  Standalone route at `/articles/{slug}/activity` with two sub-lists derived from `article_links`. Linked from the location article page.

  Events here (field_name='location', source is an event):
  ```sql
  SELECT a.slug, a.metadata_->>'event_date' as event_date,
         a.metadata_->>'outcome' as outcome
  FROM article_links al JOIN articles a ON a.id = al.source_id
  WHERE al.target_id = :location_id
    AND al.field_name = 'location'
    AND a.article_type = 'event'
    AND a.status = 'published'
  ORDER BY a.metadata_->>'event_date';
  ```

  Residents and operatives (field_name='base_of_operations', source is a profile):
  ```sql
  SELECT a.slug, a.designation, a.metadata_->>'status' as status
  FROM article_links al JOIN articles a ON a.id = al.source_id
  WHERE al.target_id = :location_id
    AND al.field_name = 'base_of_operations'
    AND a.article_type = 'profile'
    AND a.status = 'published';
  ```

  `superhero_project/routers/articles_html.py superhero_project/templates/`

- [x] **4.** `feat: add metadata filters to search`
  Extend the search endpoint (`articles_html.py:search_articles`) with optional query params for structured filtering. Filters use JSONB containment (`@>`) against the `metadata` column. `disambiguation` articles remain included in search results (they appear when a query matches the shared alias) but are excluded if `?type=` is specified and the value is not `disambiguation`.

  New params:
  ```
  ?type=profile                → WHERE article_type = 'profile'
  ?status=active               → WHERE metadata @> '{"status": "active"}'
  ?powers=flight               → WHERE metadata @> '{"powers": ["flight"]}'
  ?location_type=city          → WHERE metadata @> '{"location_type": "city"}'
  ?org_type=team               → WHERE metadata @> '{"org_type": "team"}'
  ```

  Filters compose as AND. Full-text search term remains optional — filters can be used standalone. Results page gains a filter sidebar with type-aware controls (powers filter only shown when type=profile, etc.).

  Filter params are lowercased before the JSONB query to match the normalized stored values (e.g. `?powers=Flight` → `"flight"`).
  `superhero_project/routers/articles_html.py superhero_project/templates/`
