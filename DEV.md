# Local Development

Manual testing guide for running the app end-to-end in a browser.

## Setup

Everything can run in the background from a single `devenv shell` terminal:

```sh
devenv shell
devenv up -d                                            # start PostgreSQL (detached)
uv run uvicorn superhero_project.main:app --reload &    # start app
```

To stop services:

```sh
bash scripts/kill_server.sh         # stop both (default)
bash scripts/kill_server.sh app     # stop uvicorn only
devenv processes down               # stop postgres only
```

Postgres data persists in `.devenv/state/postgres/` across restarts.

Create `.env` in the project root (one-time). Placeholder OAuth values let the
server start and the smoke test run; swap in real credentials when you register
the OAuth app (see below).

```sh
cat > .env << 'EOF'
GITHUB_CLIENT_ID=placeholder
GITHUB_CLIENT_SECRET=placeholder
SESSION_SECRET=dev-secret-change-me
EOF
```

Run migrations (one-time, after postgres is up for the first time):

```sh
uv run alembic upgrade head
```

App: http://localhost:8000 · API docs: http://localhost:8000/docs

## GitHub OAuth app

Register an OAuth App at github.com → Settings → Developer settings → OAuth Apps:

- **Homepage URL:** `http://localhost:8000`
- **Authorization callback URL:** `http://localhost:8000/auth/callback`

Copy the Client ID and generate a Client Secret; paste both into `.env`.

Create a **separate OAuth App for production** — don't share dev credentials with prod.

## Promoting a user

New accounts default to `contributor`. To test moderation, promote yourself after
signing in at least once:

```sh
uv run python scripts/promote_user.py <your-github-username> moderator
```

Sign out and back in — the session cookie caches the role.

```sh
uv run python scripts/promote_user.py <your-github-username> contributor  # demote back
```

## Manual test flows

| Flow | Entry point | What to verify |
|------|-------------|----------------|
| Create draft | New Article → pick type, fill form | Article saved as draft; profiles get `CAPE-XXXX` |
| Read draft | Click article link | Metadata sidebar, rendered Markdown body |
| Submit | Submit button on draft | Status → pending |
| Moderate | `/moderation/queue/view` | Article in queue; approve or reject |
| Read published | Article page | Visible to anon; tags shown |
| Vote | Article page | +1/−1 buttons; score updates |
| Comment | Article page | Comment appears; edit and delete work |
| Edit article | Edit button | New history entry created |
| View history | History link on article | Unified diff per revision |
| Search | `/articles/search/results?q=<term>` | Published articles ranked by relevance |
| Tag browse | `/tags` → click a tag | Articles carrying that tag |
| Contributor profile | `/contributors/<username>` | Author's published articles |

## Smoke test

Runs every endpoint against the live server without a browser. Bypasses OAuth by
seeding two DB users and crafting signed session cookies directly.

```sh
uv run python scripts/smoke.py
# uv run python scripts/smoke.py --base-url http://localhost:8000  # non-default target
```

Cleans up its own data on exit, even if checks fail.
