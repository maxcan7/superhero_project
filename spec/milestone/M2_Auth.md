# M2: Auth
Status: not started

GitHub OAuth, user model, session management, role system.

---

- [ ] **1.** `feat: add config layer with env-based settings`
  Pydantic BaseSettings reading env vars (DB URL, GitHub OAuth secrets, session key).
  `superhero_project/config.py`

- [ ] **2.** `feat: wire FastAPI app entrypoint`
  App factory, session middleware, static files mount, router includes.
  `superhero_project/main.py`

- [ ] **3.** `feat: add GitHub OAuth auth router`
  OAuth redirect + callback, token exchange, user upsert, signed-cookie session.
  `superhero_project/routers/auth.py`
