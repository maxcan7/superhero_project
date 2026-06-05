# C7: Security Hardening
Status: not started

Fixes four active vulnerabilities in the application and adds bandit to the pre-commit pipeline. No schema changes. C8 covers the complementary OAuth and rate-limiting work.

---

## Tasks

- [x] **1.** `fix(articles): disable raw HTML passthrough in markdown-it`
  `MarkdownIt()` defaults to `html: True`, which passes raw `<script>` and
  other tags straight through the renderer. Combined with `| safe` in
  `article.html`, any contributor can execute arbitrary JavaScript in readers' browsers.

  Disable both inline and block HTML:
  ```python
  _md = MarkdownIt().disable("html_block").disable("html_inline")
  ```
  The `| safe` in `article.html` remains correct — the output is now purely
  renderer-generated HTML.
  `superhero_project/routers/articles.py`

- [ ] **2.** `fix(auth): harden session cookie flags`
  `SessionMiddleware` is configured with only `secret_key`. In production the cookie must be HTTPS-only; `same_site` should be explicit.

  Add `https_only: bool = False` to `Settings` (defaults to off for local dev; set `HTTPS_ONLY=true` in the production environment). Set `same_site="lax"` unconditionally — `strict` breaks the GitHub OAuth callback because GitHub's redirect is a cross-site navigation and the browser won't attach the cookie.

  ```python
  app.add_middleware(
      SessionMiddleware,
      secret_key=settings.session_secret,
      https_only=settings.https_only,
      same_site="lax",
  )
  ```
  `superhero_project/config.py superhero_project/main.py`

- [ ] **3.** `fix(security): add security response headers middleware`
  No security headers are currently set. Add a pure ASGI middleware class in `main.py` that intercepts the `http.response.start` message and injects headers before they are sent. This is the approach used by Starlette's own built-in middlewares (`GZipMiddleware`, `HTTPSRedirectMiddleware`, etc.) and avoids the issues with `BaseHTTPMiddleware`: no response body buffering, no
  `contextvar` propagation bugs.

  ```python
  from starlette.datastructures import MutableHeaders
  from starlette.types import ASGIApp, Receive, Scope, Send

  class SecurityHeadersMiddleware:
      def __init__(self, app: ASGIApp) -> None:
          self.app = app

      async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
          if scope["type"] != "http":
              await self.app(scope, receive, send)
              return

          async def send_with_headers(message):
              if message["type"] == "http.response.start":
                  headers = MutableHeaders(scope=message)
                  headers["X-Content-Type-Options"] = "nosniff"
                  headers["X-Frame-Options"] = "DENY"
                  headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
                  headers["Content-Security-Policy"] = (
                      "default-src 'self'; script-src 'self'; style-src 'self'"
                  )
              await send(message)

          await self.app(scope, receive, send_with_headers)
  ```

  Wire it in `create_app()` via `app.add_middleware(SecurityHeadersMiddleware)`. The CSP assumes all JS and CSS is served from `/static/`. Verify against the actual template `{% block scripts %}` usage — add `'unsafe-inline'` to
  `script-src` only if inline scripts are present and cannot be removed.
  `superhero_project/main.py`

- [ ] **4.** `fix(articles): restrict non-published articles to authorized users`
  `GET /articles/{identifier}`, `GET /articles/{identifier}/history`, and the HTML view `GET /articles/{identifier}/view` all fetch by `page_name` with no status check. An unauthenticated visitor who knows a page name can read draft
  and rejected content.

  After fetching the article, apply this guard before returning:
  - If `status == published`: allow anyone.
  - Otherwise: require an authenticated user who is the author or holds
    `moderator`/`admin` role; return 403 for everyone else (including
    unauthenticated requests).

  Apply consistently to all three endpoints.
  `superhero_project/routers/articles.py superhero_project/routers/articles_html.py`

- [ ] **5.** `chore: add bandit to pre-commit`
  Add bandit as a pre-commit hook so security anti-patterns are caught locally on commit, same as ruff catches style issues.

  In `.pre-commit-config.yaml`:
  ```yaml
  - repo: https://github.com/pycqa/bandit
    rev: <latest stable tag>
    hooks:
      - id: bandit
        args: ["-c", "pyproject.toml"]
  ```

  In `pyproject.toml`, add a `[tool.bandit]` section:
  ```toml
  [tool.bandit]
  exclude_dirs = ["tests"]
  ```

  Run `pre-commit autoupdate` to pin the rev, then `pre-commit run bandit --all-files` and resolve any findings before committing.
  `.pre-commit-config.yaml pyproject.toml`
