# Superhero Universe Wiki — Spec

Corresponds to [M1](../milestone/M1_Foundation.md) · [M2](../milestone/M2_Auth.md) · [M3](../milestone/M3_Articles.md) · [M4](../milestone/M4_Moderation.md) · [M5](../milestone/M5_Community.md) · [M6](../milestone/M6_Search.md) · [M7](../milestone/M7_Content.md) · [M8](../milestone/M8_Packaging.md) · [M9](../milestone/M9_Frontend.md) · [M10](../milestone/M10_LinkGraph.md) · [M11](../milestone/M11_InfoboxesAndDerivedViews.md) · [C4](../cleanup/C4_ComicType.md)

---

## Project Philosophy

- **Collaborative fiction** over canon control: contributors own their articles, the community shapes the universe
- **Wiki-diving first**: every article should link to others; reading one should pull you deeper
- **Structured templates**: format enforced by the application
- **Minimal infrastructure**: self-hosted, no managed services at this scale

---

## Tech Stack

| Layer | Tool |
|---|---|
| Framework | **FastAPI** |
| Templating | **Jinja2** |
| ORM | **SQLAlchemy 2.x + Alembic** |
| DB (dev) | **PostgreSQL** (via devenv service) |
| DB (prod) | **PostgreSQL** (via `services.postgresql`) |
| Auth | **GitHub OAuth** |
| Markdown | **markdown-it-py** |
| Python packaging | **uv + pyproject.toml** |
| Local dev | **devenv** |
| Production packaging | **uv2nix** |
| Production system | **NixOS** |
| Reverse proxy | **Caddy** (via `services.caddy`) |
| Process management | **systemd** (via NixOS module) |

---

## Content Model

The wiki covers two layers simultaneously, like Wikipedia's treatment of comics: **in-universe** content (what happens within the fiction) and **meta** content (the real-world publication context of the fiction). Neither layer is secondary. A wiki about a superhero should cover both the character's biography and the history of the comics that tell it.

Eight article types, each with a strict template. All articles have a YAML frontmatter block with required metadata fields and a `schema_version` field, followed by freeform Markdown narrative sections.

### In-universe types

### 1. Profile (`profile/`)

The core unit. Each profile covers a hero, villain, or otherwise notable individual.

### 2. Event (`event/`)

Articles covering battles, disasters, first appearances, turning points. The connective tissue for wiki-diving.

### 3. Organization (`org/`)

Teams, agencies, corporations, cults — and publishing organizations (`org_type: publisher`). Publisher orgs are the bridge between the in-universe and meta layers; they are real-world entities within the fiction rather than in-universe organizations the characters interact with directly.

### 4. Location (`location/`)

Cities, bases, anomalous zones.

### 5. Technology / Artifact (`tech/`)

Gear, serums, relics.

### 6. Lore (`lore/`)

In-universe world-building entries: power classification systems, historical events, in-universe laws. No single author — community-maintained.

### Meta types

### 7. Comic (`comic/`)

A comic series or property, covering all publisher runs. The meta counterpart to a profile: where the profile covers who Mercury Maimonides is, the comic article covers the history of the Rebis Bondi series that tells her story. Metadata: publishers (linked list), first/last issue, status, comic type.

### 8. Disambiguation (`disambiguation/`)

Named lists of articles that share an alias. When `[[Mercury]]` is ambiguous, it resolves to a disambiguation page rather than failing. Authored and managed by moderators; excluded from article feeds but searchable.

---

## Article Naming Convention

`CAPE-XXXX` for profiles (4-digit number, auto-assigned by DB sequence).
All other types use slug-based naming (`event/the-chicago-collapse`, `org/the-patrol`).

---

## Database Schema

Per-type metadata fields live in a JSONB column, validated at the application layer against each type's Pydantic schema. This keeps the DB schema stable as field definitions evolve.

```sql
users (
  id, github_id, github_username, display_name,
  role,            -- contributor | moderator | admin
  created_at
)

articles (
  id, slug, article_type, designation,
  schema_version,
  metadata JSONB,  -- per-type required fields, validated in app
  content TEXT,    -- raw Markdown body
  author_id REFERENCES users(id),
  status,          -- draft | pending | published | rejected
  created_at, updated_at, published_at,
  search_vector TSVECTOR  -- maintained by trigger for full-text search
)

article_tags (article_id, tag)

votes (
  id, article_id REFERENCES articles(id),
  user_id REFERENCES users(id),
  value SMALLINT,  -- +1 or -1
  created_at,
  UNIQUE(article_id, user_id)
)

comments (
  id, article_id REFERENCES articles(id),
  author_id REFERENCES users(id),
  body TEXT,
  created_at, updated_at
)

article_history (
  id, article_id REFERENCES articles(id),
  editor_id REFERENCES users(id),
  metadata_snapshot JSONB,
  content_snapshot TEXT,
  edited_at
)

article_links (
  id, source_id REFERENCES articles(id),
  target_id REFERENCES articles(id),
  field_name VARCHAR,   -- NULL = wikilink body; named = metadata edge (e.g. "affiliation")
  resolved_via VARCHAR  -- the alias string that resolved to target_id
)
```

---

## Auth: GitHub OAuth

1. User clicks "Sign in with GitHub"
2. GitHub redirects back with a code; server exchanges it for a token
3. Server fetches GitHub user profile, upserts a `users` row
4. Session stored server-side (signed cookie or JWT)

Roles:
- **Contributor**: submit articles, comment, vote
- **Moderator**: approve/reject submissions, edit any article
- **Admin**: promote users, manage site config

---

## Contribution Workflow

1. Authenticated user opens in-app editor, selects article type
2. Fills required metadata fields (form-driven, validated against type schema)
3. Writes Markdown body with live preview
4. Submits → article saved as `status: pending`, moderators notified
5. Moderator reviews in moderation queue: approve, request changes, or reject with note
6. Approved → `status: published`, visible immediately

---

## Features

- User accounts with contribution history
- In-app article editor with Markdown preview
- Moderation queue
- Voting (+1/−1 per article, one vote per user)
- Comments on article pages
- Article edit history with diffs
- Full-text search via Postgres `tsvector`
- Tag browsing with article counts
- Contributor profiles listing authored articles
- Wikilinks (`[[Entity Name]]`) in article bodies resolve to linked articles; unresolved links render as red stubs pre-filled for creation
- Article link graph: "References" and "Referenced by" panels derived from wikilinks and metadata edges
- Disambiguation pages for shared aliases
- Per-type infoboxes rendering structured metadata (status chips, linked lists, text badges)
- Derived views: org member roster, location event history and residents
- Metadata filters in search (`?type=`, `?status=`, `?powers=`, etc.)

---

## Application Structure

```
superhero_project/
  main.py
  config.py
  dependencies.py
  db/
    models.py
    session.py
  domain/
    profile.py
    event.py
    org.py
    location.py
    tech.py
    lore.py
    disambiguation.py
    links.py
  routers/
    _utils.py
    articles.py
    articles_html.py
    auth.py
    comments.py
    community.py
    moderation.py
    votes.py
  templates/
    base.html
    index.html
    article.html
    editor.html
    history.html
    search.html
    infobox/
      profile.html
      event.html
      org.html
      location.html
      tech.html
      lore.html
    contributors/
      profile.html
    me/
      articles.html
    moderation/
      queue.html
    tags/
      index.html
      detail.html
  static/
    css/
      main.css
    ts/               ← TypeScript source
    js/               ← compiled output (esbuild)
alembic/
scripts/
tests/
spec/
flake.nix
devenv.nix
nix/
  module.nix
  server.nix
pyproject.toml
uv.lock
tsconfig.json
```

---

## Deployment

```
VPS (NixOS)
├── services.caddy      — reverse proxy, automatic TLS
├── services.postgresql — data in /var/lib/postgresql
└── systemd unit        — FastAPI via uvicorn, defined in nix/module.nix
```

Deploy: `nixos-rebuild switch --flake .#server --target-host user@host`
Rollback: `nixos-rebuild switch --rollback`
Backups: `pg_dump` on a systemd timer declared in the NixOS config.

---

## Portability

The `flake.nix` defines the entire server configuration. Moving providers is provisioning a NixOS machine and pointing DNS.

---

## Cost Estimate

| Component | ~Annual Cost |
|---|---|
| VPS (2 vCPU, 4GB RAM) — Hetzner CX22 / Linode 4GB / Lightsail 4GB | $50–85 |
| Domain — Cloudflare at-cost (~$9) or Namecheap (~$12) | $9–15 |
| DNS — Cloudflare free tier | $0 |
| **Total** | **~$60–100/yr** |

At meaningful scale, move Postgres to a managed instance and upgrade the VPS.

---

## Milestone Plan

| Milestone | Contents |
|---|---|
| [M1: Foundation](../milestone/M1_Foundation.md) | Project skeleton, DB models, Alembic migrations, devenv + NixOS module |
| [M2: Auth](../milestone/M2_Auth.md) | GitHub OAuth, user model, session management, role system |
| [M3: Articles](../milestone/M3_Articles.md) | Article CRUD, per-type Pydantic schemas, Markdown rendering, slug routing |
| [M4: Moderation](../milestone/M4_Moderation.md) | Submission workflow, moderation queue, status transitions |
| [M5: Community](../milestone/M5_Community.md) | Voting, comments, contributor profiles, tag browsing |
| [M6: Search](../milestone/M6_Search.md) | Postgres full-text search, search UI |
| [M7: Content](../milestone/M7_Content.md) | Style guide, canon rules, seed articles to establish tone and demonstrate wiki-diving |
| [M8: Packaging](../milestone/M8_Packaging.md) | uv2nix build, NixOS module wiring, end-to-end deployment verification |
| [M9: Frontend](../milestone/M9_Frontend.md) | Nav, article actions, vote/comment UI, editor, my-articles page, TypeScript toolchain |
| [M10: Link Graph](../milestone/M10_LinkGraph.md) | Wikilinks, alias index, metadata edge extraction, reference panels, disambiguation pages |
| [M11: Infoboxes & Derived Views](../milestone/M11_InfoboxesAndDerivedViews.md) | Per-type infobox templates, org member roster, location activity view, metadata search filters |
