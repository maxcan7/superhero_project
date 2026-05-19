# C5: Split infobox display logic out of links.py
Status: complete

`links.py` has grown to ~440 lines. The infobox code added in M11 is the only part
that is genuinely a different abstraction — it takes raw edge data and formats it for template rendering, rather than maintaining the link graph. Everything else in the file (alias index building, wikilink rendering/sync, metadata edge sync, fetch functions, backfill) is raw graph operation and belongs together.

Extract the infobox display logic into its own focused module.

---

- [x] **1.** `refactor(links): extract infobox display logic to infobox.py`
  Create `superhero_project/domain/infobox.py` containing:
  - `ResolvedLink`, `UnresolvedLink`, `InboxLinkItem` (TypedDicts)
  - `_field_edge_map`, `_resolve_field_values`, `build_infobox_links`

  `infobox.py` imports `_HANDLERS` from `links.py` and `normalize_str` from `_utils`.

  `links.py` loses only those names; everything else stays.

  Update `routers/articles_html.py` to import `build_infobox_links` and the
  TypedDicts from `superhero_project.domain.infobox`.

  Create `tests/test_infobox.py` with the `build_infobox_links` parametrized tests
  moved from `test_links.py`, updated to import from `superhero_project.domain.infobox`.
  Coverage must remain at 100%.
  `superhero_project/domain/links.py superhero_project/domain/infobox.py superhero_project/routers/articles_html.py tests/test_links.py tests/test_infobox.py`
