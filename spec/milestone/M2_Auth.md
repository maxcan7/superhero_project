# M2: Auth
Status: complete

GitHub OAuth, user model, session management, role system.

---

- [x] **1.** `feat: add config layer with env-based settings`
  Pydantic BaseSettings reading env vars (DB URL, GitHub OAuth secrets, session key).
  Add FastAPI/uvicorn/httpx/pydantic-settings/aiofiles deps and pydantic mypy plugin.
  `pyproject.toml superhero_project/config.py`

- [x] **2.** `feat: wire FastAPI app entrypoint and GitHub OAuth auth router`
  App factory, session middleware, static files mount, router includes.
  OAuth redirect + callback, token exchange, user upsert, signed-cookie session.
  `superhero_project/main.py superhero_project/py.typed superhero_project/routers/__init__.py superhero_project/routers/auth.py static/.gitkeep`
