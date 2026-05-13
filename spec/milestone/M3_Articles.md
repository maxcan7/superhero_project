# M3: Articles
Status: complete

Article CRUD, per-type Pydantic schemas, Markdown rendering, slug routing.

---

- [x] **1.** `feat: add per-type Pydantic metadata schemas`
  One Pydantic model per article type; validates JSONB metadata at the app layer.
  `superhero_project/domain/profile.py superhero_project/domain/event.py superhero_project/domain/org.py superhero_project/domain/location.py superhero_project/domain/tech.py superhero_project/domain/lore.py`

- [x] **2.** `feat: add articles router with CRUD, slug routing, and Markdown rendering`
  Create/read/update/delete; designation routing for profiles, slug routing for all others; markdown-it-py body rendering.
  `superhero_project/routers/articles.py`

- [x] **3.** `feat: add base and article Jinja2 templates`
  HTML shell with nav, article view (metadata sidebar + rendered body), front page.
  `superhero_project/templates/base.html superhero_project/templates/article.html superhero_project/templates/index.html`

- [x] **4.** `feat: add static assets`
  Base stylesheet; JS for live Markdown preview in the editor.
  `superhero_project/static/css/ superhero_project/static/js/`
