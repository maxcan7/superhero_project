# C8: Auth CSRF & Rate Limiting
Status: not started

Adds an OAuth state nonce to prevent login CSRF, and introduces rate limiting
across auth and write endpoints via `slowapi`. No schema changes. Complements
the hardening in C7.

---

## Tasks

- [ ] **1.** `fix(auth): add OAuth state nonce to prevent login CSRF`
  The `/auth/login` → `/auth/callback` flow sends no `state` parameter.
  An attacker can initiate an OAuth flow and trick a user into completing it,
  binding the victim's session to the attacker's GitHub identity.

  On `/auth/login`: generate a `secrets.token_urlsafe(32)` nonce, store it in
  the session as `"oauth_state"`, and include it as the `state` parameter in
  the GitHub authorization URL.

  On `/auth/callback`: accept `state: str` as a query parameter. Pop
  `"oauth_state"` from the session and compare — if missing or mismatched,
  redirect to `/` without completing login (same behaviour as the existing
  `httpx.HTTPError` path).

  ```python
  # login
  state = secrets.token_urlsafe(32)
  request.session["oauth_state"] = state
  params = urlencode({..., "state": state})

  # callback
  async def callback(request: Request, code: str, state: str, db: DB):
      if state != request.session.pop("oauth_state", None):
          return RedirectResponse("/")
      ...
  ```
  `superhero_project/routers/auth.py`

- [ ] **2.** `feat(security): add rate limiting via slowapi`
  No endpoints are rate-limited. Add `slowapi` (wraps the `limits` library,
  idiomatic for FastAPI) and apply per-IP limits to auth and high-risk write
  endpoints. For this deployment (single-process systemd unit per M8),
  in-memory storage is sufficient; a Redis backend can be swapped in later via
  the `slowapi` storage URI.

  Add `slowapi` to `pyproject.toml` dependencies, then `uv sync`.

  Wire into the app in `main.py`:
  ```python
  from slowapi import Limiter, _rate_limit_exceeded_handler
  from slowapi.errors import RateLimitExceeded
  from slowapi.util import get_remote_address

  limiter = Limiter(key_func=get_remote_address)
  app.state.limiter = limiter
  app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
  ```

  Apply limits with the `@limiter.limit(...)` decorator. Suggested limits:

  | Endpoint | Limit |
  |---|---|
  | `GET /auth/login` | 20/minute |
  | `GET /auth/callback` | 20/minute |
  | `POST /articles/` | 30/hour |
  | `POST /articles/render` | 60/minute |
  | `POST /comments/{identifier}` | 30/minute |

  All decorator-decorated route functions must accept `request: Request` as a
  parameter (already the case for auth and comment routes; verify for any that
  don't currently take it).
  `pyproject.toml superhero_project/main.py superhero_project/routers/auth.py superhero_project/routers/articles.py superhero_project/routers/comments.py`
