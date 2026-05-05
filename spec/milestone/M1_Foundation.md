# M1: Foundation
Status: in-progress

Project skeleton, DB models, Alembic migrations, devenv + NixOS module.

---

- [x] **1.** `chore: init project with uv and pyproject.toml`
  Bootstrap Python packaging; pin runtime deps.
  `pyproject.toml uv.lock`

- [x] **2.** `chore: add devenv and Nix flake for local dev`
  Define local dev environment with PostgreSQL service.
  `devenv.nix flake.nix`

- [x] **3.** `chore: add NixOS module and server config`
  Systemd unit, Caddy reverse proxy, pg_dump backup timer.
  `nix/meta.nix nix/module.nix nix/server.nix`

- [x] **4.** `feat: add SQLAlchemy models and session factory`
  All ORM models: users, articles, article_tags, votes, comments, article_history.
  `superhero_project/db/models.py superhero_project/db/session.py`

- [ ] **5.** `chore: init Alembic and generate initial migration`
  Alembic config + first migration creating all tables.
  `alembic/ alembic/versions/<hash>_init.py`
