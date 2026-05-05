# M1: Foundation
Status: not started

Project skeleton, DB models, Alembic migrations, devenv + NixOS module.

---

- [ ] **1.** `chore: init project with uv and pyproject.toml`
  Bootstrap Python packaging; pin runtime deps.
  `pyproject.toml uv.lock`

- [ ] **2.** `chore: add devenv and Nix flake for local dev`
  Define local dev environment with PostgreSQL service.
  `devenv.nix flake.nix`

- [ ] **3.** `chore: add NixOS module and server config`
  Systemd unit, Caddy reverse proxy, pg_dump backup timer.
  `nix/module.nix nix/server.nix`

- [ ] **4.** `feat: add SQLAlchemy models and session factory`
  All ORM models: users, articles, article_tags, votes, comments, article_history.
  `superhero_project/db/models.py superhero_project/db/session.py`

- [ ] **5.** `chore: init Alembic and generate initial migration`
  Alembic config + first migration creating all tables.
  `alembic/ alembic/versions/<hash>_init.py`
