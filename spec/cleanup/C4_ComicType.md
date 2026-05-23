# C4: Comic Article Type and Publisher Org Type
Status: complete

Retroactively adds the meta layer to the content model. The wiki covers both in-universe
content (character biographies, events, organizations, locations, tech, lore) and the
real-world publication context of the fiction (comic series, publisher runs). This mirrors
the Wikipedia approach to superhero articles, which interleave in-universe biography with
publication history. Neither layer is secondary.

This spec adds:

- A `comic` article type for comic series and properties (the "real-world within the fiction"
  layer).
- A `publisher` value to `OrgType` so that publishing organizations (Adad Magazine,
  Fantagraphics, TMP) are distinguishable from in-universe organizations (S.H.I.E.L.D., BLiP
  Cult) at the schema level.

No existing article types are changed. This is purely additive.

---

## Article type: `comic`

A comic article covers a series or property across all its publisher runs. Individual runs
live in the body; the metadata captures the canonical or current state.

```
ComicMetadata:
  comic_type   series | miniseries | one_shot | anthology | other
  publishers   list[str]   — each resolves via alias index (M10 edge: "publishers")
  first_issue  str | None  — e.g. "Adad Magazine Issue 3 (1987)"
  last_issue   str | None
  status       ongoing | completed | cancelled | unknown
```

Page name convention: same for all types (`rebis-bondi`, `ms-marvel`).

---

## OrgType addition: `publisher`

Extends `OrgType` with `publisher` to distinguish real-world publishing organizations from
in-universe ones. No new article type or metadata schema is needed; `OrgMetadata` already
has `aliases`, `headquarters`, `founded`, `status`, and `affiliation`.

---

## M10 / M11 updates

`ComicMetadata.publishers` is a list field that participates in the M10 metadata edge
extractor, creating `field_name = "publishers"` edges to resolved publisher org articles.

M11 comic infobox rendering:
```
comic_type   → chip
publishers   → linked list (via alias index; plain text if unresolved)
first_issue  → plain text
last_issue   → plain text
status       → colored chip: ongoing=green, completed=grey, cancelled=red, unknown=grey
```

---

## Tasks

- [x] **1.** `feat: add publisher to OrgType`
  Add `publisher = "publisher"` to `OrgType` in `domain/org.py`. Alembic migration to
  extend the `org_type` PostgreSQL enum:
  ```sql
  ALTER TYPE org_type ADD VALUE 'publisher';
  ```
  `superhero_project/domain/org.py alembic/versions/<hash>_add_publisher_org_type.py`

- [x] **2.** `feat: add comic article type`
  New `domain/comic.py` with `ComicType`, `ComicStatus`, and `ComicMetadata`. Add `comic`
  to `ArticleType` in `db/models.py`. Register `ComicMetadata` in `_METADATA_SCHEMAS` in
  `routers/articles.py`. Alembic migration:
  ```sql
  ALTER TYPE article_type ADD VALUE 'comic';
  ```
  `superhero_project/domain/comic.py superhero_project/db/models.py superhero_project/routers/articles.py alembic/versions/<hash>_add_comic_article_type.py`

- [x] **3.** `docs: update M10 field mapping for comic`
  Add `ComicMetadata.publishers (list[str]) → field_name = "publishers"` to the metadata
  edge extractor field mapping table in M10.
  `spec/milestone/M10_LinkGraph.md`

- [x] **4.** `docs: update M11 infobox spec for comic`
  Add comic infobox rendering rules (see above) to M11.
  `spec/milestone/M11_InfoboxesAndDerivedViews.md`
