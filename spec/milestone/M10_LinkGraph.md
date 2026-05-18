# M10: Link Graph
Status: in-progress

Entity relationship graph: wikilinks in article bodies, typed edges from domain metadata fields, and reference panels showing connections between articles.

---

## Overview

Every article save triggers two edge-extraction passes that write into a single `article_links` join table. Both passes use a shared alias index to resolve free-text strings (slugs, human names, aliases) to article IDs. The edge table is then queried at read time to render two panels on every article page.

```
                ┌──────────────────────────────────────┐
                │          Article (on save)           │
                └───────────────┬──────────────────────┘
                                │
              ┌─────────────────┴──────────────────┐
              ▼                                     ▼
    ┌───────────────────┐               ┌───────────────────────┐
    │  Wikilink parser  │               │  Metadata extractor   │
    │  [[Entity Name]]  │               │  affiliation,         │
    │  [[Name|Display]] │               │  participants,        │
    └────────┬──────────┘               │  notable_residents,   │
             │                          │  location, …          │
             │                          └──────────┬────────────┘
             │                                     │
             └─────────────┬───────────────────────┘
                           │  resolve via alias index
                           ▼
                 ┌──────────────────────┐
                 │    article_links     │
                 │  source_id  BIGINT   │
                 │  target_id  BIGINT   │
                 │  field_name VARCHAR  │  ← NULL = wikilink
                 └──────────────────────┘
                           │
              ┌────────────┴────────────┐
              ▼                         ▼
    ┌─────────────────┐      ┌──────────────────────┐
    │  "References"   │      │   "Referenced by"    │
    │  panel          │      │   panel              │
    │  (outgoing)     │      │   (incoming)         │
    └─────────────────┘      └──────────────────────┘
```

The alias index is the shared lookup that makes both passes work. It maps every normalized string that could identify an article — slugs, designations, and per-type alias fields — to an article ID.

---

## Tasks

- [x] **1.** `feat: add article_links migration`
  `article_links` table with source/target foreign keys and a nullable `field_name` column distinguishing wikilinks (NULL) from named metadata edges. Indexed in both directions for fast panel queries.

  ```sql
  CREATE TABLE article_links (
      id           BIGSERIAL PRIMARY KEY,
      source_id    BIGINT NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
      target_id    BIGINT NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
      field_name   VARCHAR(100),   -- NULL = wikilink; named = metadata edge
      resolved_via VARCHAR(255),   -- the alias string that resolved to target_id
      UNIQUE (source_id, target_id, field_name)
  );
  CREATE INDEX article_links_source_idx ON article_links(source_id);
  CREATE INDEX article_links_target_idx ON article_links(target_id);
  ```

  `resolved_via` stores the exact alias string used to resolve the edge (e.g. `"tony stark"`). When an alias is removed from an article, edges where `resolved_via` matches the removed alias can be deleted directly without re-parsing all referencing articles. The UNIQUE constraint on `(source_id, target_id, field_name)` means a profile can be linked to an org both by a wikilink (field_name NULL) and by an `affiliation` metadata edge — two distinct, meaningful edges.
  `alembic/versions/<hash>_article_links.py`

- [ ] **2.** `feat: add alias index`
  A flat dict mapping normalized strings to article IDs, built from all published articles. "Normalized" means lowercased and whitespace-stripped.

  Sources per type:
  ```
  All types:    slug                          e.g. "avengers", "metropolis"
  Profile:      designation                   e.g. "cape-0001"
                ProfileMetadata.aliases       e.g. ["Iron Man", "Tony Stark"]
  Org:          OrgMetadata.aliases           e.g. ["S.H.I.E.L.D.", "Shield"]
  ```

  Interface:
  ```python
  # superhero_project/domain/links.py
  AliasIndex = dict[str, int]  # normalized text → article_id

  async def build_alias_index(db: AsyncSession) -> AliasIndex:
      ...
  ```

  Collision policy: when a moderation approval would cause an alias to be claimed by two different articles, the moderator is prompted to resolve it — either by adding a qualifier to one article's slug/aliases (e.g., "Mercury (villain)" vs "Mercury (hero)"), or by creating a disambiguation page at the shared alias (see Task 6). The alias index only maps unambiguous aliases; a shared alias that has been flagged for disambiguation is excluded from the index and handled separately.
  `superhero_project/domain/links.py`

- [ ] **3.** `feat: add wikilink parser and renderer`
  Scans `[[...]]` patterns from article body on save. Supports optional display text: `[[Entity Name|Display Text]]`.

  Regex: `r'\[\[([^\]|]+?)(?:\|[^\]]+?)?\]\]'`

  On save flow:
  1. Delete all existing wikilink edges for this source (`field_name IS NULL`)
  2. Find all `[[...]]` matches in body
  3. Normalize each target string, look up in alias index
  4. Upsert resolved edges into `article_links` — unresolved targets are silently dropped. Use `ON CONFLICT (source_id, target_id, field_name) DO UPDATE SET resolved_via = EXCLUDED.resolved_via` to handle the case where the same edge is re-resolved via a different alias.

  Renderer (called at read time inside `_render()`):
  - Resolved: `[[Entity Name]]` → `<a href="/articles/{slug}">Entity Name</a>`
  - Resolved with display text: `[[Entity Name|Display]]` → `<a href="/articles/{slug}">Display</a>`
  - Unresolved: render as a red link — `<a href="/articles/new?slug={normalized}" class="red-link">Entity Name</a>` — styled in red/muted to signal the article doesn't exist yet, but clickable to pre-fill the article creation form with that slug
  `superhero_project/domain/links.py superhero_project/routers/articles.py`

- [ ] **4.** `feat: add metadata edge extractor`
  Walks the domain metadata fields that carry relationship values and writes typed edges using the same alias index.

  Field mapping:
  ```
  ProfileMetadata:
    affiliation (list[str])       → field_name = "affiliation"
    base_of_operations (str)      → field_name = "base_of_operations"

  EventMetadata:
    location (str)                → field_name = "location"
    participants (list[str])      → field_name = "participants"

  OrgMetadata:
    headquarters (str)            → field_name = "headquarters"
    affiliation (list[str])       → field_name = "affiliation"

  LocationMetadata:
    notable_residents (list[str]) → field_name = "notable_residents"

  TechMetadata:
    current_holder (str)          → field_name = "current_holder"

  LoreMetadata:
    related_articles (list[str])  → field_name = "related_articles"

  ComicMetadata:
    publishers (list[str])        → field_name = "publishers"
  ```

  On save: delete all existing metadata edges for this source (`field_name IS NOT NULL`), re-extract, insert resolved edges. Called in the same save path as the wikilink parser, after `_validate_metadata`.
  `superhero_project/domain/links.py superhero_project/routers/articles.py`

- [ ] **5.** `feat: add reference panels to article template`
  Two panels rendered below the article body, both derived from `article_links`.

  Outgoing ("References" — what this article links to):
  ```sql
  SELECT a.slug, a.article_type, al.field_name
  FROM article_links al JOIN articles a ON a.id = al.target_id
  WHERE al.source_id = :id AND a.status = 'published'
  ORDER BY al.field_name NULLS FIRST, a.article_type;
  ```

  Incoming ("Referenced by" — articles that link here):
  ```sql
  SELECT a.slug, a.article_type, al.field_name
  FROM article_links al JOIN articles a ON a.id = al.source_id
  WHERE al.target_id = :id AND a.status = 'published'
  ORDER BY a.article_type;
  ```

  Panel display: wikilink edges (field_name NULL) grouped under "Mentioned in body"; metadata edges grouped by field_name (e.g., "Via: affiliation", "Via: participants"). Each entry is a linked article chip showing type badge + slug.
  `superhero_project/templates/article.html superhero_project/static/css/`

- [ ] **6.** `feat: backfill edges on publish and alias change`
  Two triggers both require re-parsing wikilinks in other articles: publishing a new article (previously-unresolved `[[Entity Name]]` edges can now resolve) and editing an article's aliases (added aliases open new resolutions; removed aliases may invalidate existing edges).

  On publish:
  1. Update alias index to include the newly-published article
  2. Collect the article's slug + all aliases
  3. Query all other published articles whose `content` contains any of those strings (`ILIKE` or existing tsvector)
  4. Re-run the wikilink parser for each match

  On alias edit (aliases added or removed):
  1. Diff old aliases vs new aliases
  2. For added aliases: same as publish flow above, scoped to the new aliases only
  3. For removed aliases: `DELETE FROM article_links WHERE target_id = :article_id AND resolved_via = :removed_alias`

  Both run synchronously within the same transaction. At this scale a background task queue is not warranted.
  `superhero_project/routers/moderation.py superhero_project/routers/articles.py superhero_project/domain/links.py`

- [ ] **7.** `feat: add disambiguation pages`
  A new article type — `disambiguation` — that acts as a named list of articles sharing the same alias. When `[[Mercury]]` is ambiguous, it resolves to the disambiguation page rather than failing silently or picking arbitrarily.

  Authoring model (Wikipedia convention):
  - A disambiguation article has its slug set to the shared name (e.g., "mercury")
  - Its body lists the articles that share that name, with a `[[Qualifier]]` wikilink to each (e.g., `[[Mercury (villain)]]`, `[[Mercury (hero)]]`)
  - Authors can bypass disambiguation by using the qualified form directly: `[[Mercury (villain)]]` resolves straight to the target article without going through the disambiguation page

  Alias index behaviour:
  - A slug held by a disambiguation article is excluded from direct resolution
  - `[[Mercury]]` → renders as a link to the disambiguation page
  - `[[Mercury (villain)]]` → resolves normally via the qualified alias

  Creation flow: when a moderation approval would create a collision, the moderator is prompted to either add a qualifier to the incoming article's aliases, or create (or nominate an existing) disambiguation page at the shared alias. Disambiguation articles skip the normal pending → published moderation flow — they can be created directly by moderators and admins.

  Metadata schema: disambiguation articles carry no domain-specific metadata. Add a `DisambiguationMetadata` model with no fields (just `model_config = ConfigDict(extra="forbid")`) and register it in `_METADATA_SCHEMAS` so the router doesn't error on create.

  Visibility: excluded from article feeds and listings — they are not content. They do appear in search results when a query matches the shared alias.
  `superhero_project/db/models.py superhero_project/domain/disambiguation.py superhero_project/domain/links.py superhero_project/templates/`
