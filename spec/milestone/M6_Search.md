# M6: Search
Status: complete

Postgres full-text search, search UI.

---

- [x] **1.** `feat: add tsvector column and full-text search migration`
  Add tsvector column to articles; Postgres trigger to keep it current on insert/update.
  `alembic/versions/<hash>_fts.py`

- [x] **2.** `feat: add search endpoint and results template`
  Full-text search via `@@` operator; ranked results page.
  `superhero_project/routers/articles.py superhero_project/templates/`
