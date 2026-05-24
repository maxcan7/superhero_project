#!/usr/bin/env python3
"""Smoke test against a running local server.

Bypasses GitHub OAuth by inserting smoke-test users directly into the DB
and crafting signed session cookies, mirroring the test suite approach.

Prerequisites (in order):
  1. devenv up                              # starts PostgreSQL on 127.0.0.1:5433
  2. devenv shell                           # sets DATABASE_URL in env
  3. .env with SESSION_SECRET               # read by pydantic-settings
  4. alembic upgrade head                   # schema must be current
  5. uvicorn superhero_project.main:app --reload &

Usage (from project root, inside devenv shell):
  uv run python scripts/smoke.py [--base-url http://localhost:8000]

Exit code: 0 if all checks pass, 1 if any fail.
"""

from __future__ import annotations

import argparse
import json
import sys
from base64 import b64encode
from dataclasses import dataclass
from dataclasses import field
from typing import Any

import httpx
import itsdangerous
import psycopg

from superhero_project.config import settings

# Sentinel values — high github_ids and distinctive usernames that won't
# collide with real accounts.
_CONTRIB_GH_ID = 9_999_997
_CONTRIB_USERNAME = "smoke-contrib"
_MOD_GH_ID = 9_999_998
_MOD_USERNAME = "smoke-mod"
_EVENT_SLUG = "smoke-event-001"

_PROFILE_META: dict[str, Any] = {
    "aliases": ["Smokescreen"],
    "powers": ["invisibility", "confusion"],
    "status": "active",
    "affiliation": [],
    "base_of_operations": "Smoke City",
    "first_appearance": None,
}

_EVENT_META: dict[str, Any] = {
    "event_date": "2025-06-01",
    "location": "Smoke City",
    "participants": [],
    "outcome": None,
}


# ── Shared context ─────────────────────────────────────────────────────────────


@dataclass
class _Ctx:
    """Shared state for a smoke test run: HTTP clients and failure accumulator."""

    contrib: httpx.Client
    mod: httpx.Client
    anon: httpx.Client
    failures: list[str] = field(default_factory=list)


# ── Utilities ──────────────────────────────────────────────────────────────────


def _cookie(user_id: int, role: str) -> str:
    """Return a Starlette-compatible signed session cookie."""
    payload = b64encode(json.dumps({"user_id": user_id, "role": role}).encode())
    return itsdangerous.TimestampSigner(settings.session_secret).sign(payload).decode()


def _psycopg_url() -> str:
    """Strip asyncpg driver prefix so psycopg can use the URL."""
    return settings.database_url.replace("postgresql+asyncpg://", "postgresql://", 1)


def _check(ctx: _Ctx, label: str, resp: httpx.Response, expected: int) -> bool:
    """Print a pass/fail line; append label to ctx.failures if status mismatches."""
    ok = resp.status_code == expected
    suffix = "" if ok else f"  (got {resp.status_code})"
    print(f"  {'✓' if ok else '✗'} {label}{suffix}")
    if not ok:
        ctx.failures.append(label)
    return ok


# ── Database helpers ───────────────────────────────────────────────────────────


def _find_stale_smoke_users(
    conn: psycopg.Connection,
) -> tuple[int | None, int | None]:
    """Return DB ids of any leftover smoke users, or None if absent."""
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM users WHERE github_id = %s", (_CONTRIB_GH_ID,))
        row = cur.fetchone()
        contrib = row[0] if row else None
        cur.execute("SELECT id FROM users WHERE github_id = %s", (_MOD_GH_ID,))
        row = cur.fetchone()
        mod = row[0] if row else None
    return contrib, mod


def _delete_smoke_data(
    conn: psycopg.Connection, contrib_id: int | None, mod_id: int | None
) -> None:
    """Delete smoke-test articles (and their children) then the smoke users."""
    with conn.cursor() as cur:
        if contrib_id is not None:
            cur.execute("SELECT id FROM articles WHERE author_id = %s", (contrib_id,))
            article_ids = [r[0] for r in cur.fetchall()]
            if article_ids:
                ph = ",".join(["%s"] * len(article_ids))
                for tbl in ("article_tags", "votes", "comments", "article_history"):
                    cur.execute(
                        f"DELETE FROM {tbl} WHERE article_id IN ({ph})", article_ids
                    )
                cur.execute(f"DELETE FROM articles WHERE id IN ({ph})", article_ids)
        for uid in (u for u in (contrib_id, mod_id) if u is not None):
            cur.execute("DELETE FROM users WHERE id = %s", (uid,))
    conn.commit()


def _pre_cleanup(conn: psycopg.Connection) -> None:
    """Remove any leftover smoke data from a previous failed run."""
    stale_c, stale_m = _find_stale_smoke_users(conn)
    if stale_c or stale_m:
        print("Removing leftover data from a previous run...")
        _delete_smoke_data(conn, stale_c, stale_m)


def _seed_users(conn: psycopg.Connection) -> tuple[int, int]:
    """Insert the smoke contributor and moderator users; return their ids."""
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO users "
            "(github_id, github_username, display_name, role) "
            "VALUES (%s, %s, 'Smoke Contributor', 'contributor') RETURNING id",
            (_CONTRIB_GH_ID, _CONTRIB_USERNAME),
        )
        contrib_id: int = cur.fetchone()[0]  # type: ignore[index]
        cur.execute(
            "INSERT INTO users "
            "(github_id, github_username, display_name, role) "
            "VALUES (%s, %s, 'Smoke Moderator', 'moderator') RETURNING id",
            (_MOD_GH_ID, _MOD_USERNAME),
        )
        mod_id: int = cur.fetchone()[0]  # type: ignore[index]
    conn.commit()
    return contrib_id, mod_id


# ── Check groups ───────────────────────────────────────────────────────────────


def _check_static(ctx: _Ctx) -> None:
    """Check that no-auth pages are reachable."""
    print("No-auth pages:")
    _check(ctx, "GET /", ctx.anon.get("/"), 200)
    _check(ctx, "GET /articles/search", ctx.anon.get("/articles/search"), 200)
    _check(ctx, "GET /tags", ctx.anon.get("/tags"), 200)


def _create_articles(ctx: _Ctx) -> str | None:
    """Create a profile and an event article; return the profile slug."""
    print("\nCreate articles:")
    r = ctx.contrib.post(
        "/articles/",
        json={
            "article_type": "profile",
            "page_name": "smoke-profile",
            "metadata": _PROFILE_META,
            "content": "# Smokescreen\n\nA hero shrouded in mystery.",
            "tags": ["smoke-test", "hero"],
        },
    )
    _check(ctx, "POST /articles/ (profile)", r, 201)
    profile_slug = r.json()["page_name"] if r.status_code == 201 else None

    _check(
        ctx,
        "POST /articles/ (event)",
        ctx.contrib.post(
            "/articles/",
            json={
                "article_type": "event",
                "page_name": _EVENT_SLUG,
                "metadata": _EVENT_META,
                "content": "# The Smoke Incident\n\nIt happened fast.",
                "tags": ["smoke-test"],
            },
        ),
        201,
    )

    print("\nMarkdown render:")
    _check(
        ctx,
        "POST /articles/render",
        ctx.contrib.post("/articles/render", json={"content": "**hello**"}),
        200,
    )

    return profile_slug


def _check_article_read(ctx: _Ctx, profile_slug: str) -> None:
    """Check JSON and HTML views of an article."""
    print("\nRead article:")
    _check(
        ctx,
        f"GET /articles/{profile_slug} (JSON)",
        ctx.anon.get(f"/articles/{profile_slug}"),
        200,
    )
    _check(
        ctx,
        f"GET /articles/{profile_slug}/view (HTML)",
        ctx.anon.get(f"/articles/{profile_slug}/view"),
        200,
    )


def _check_article_update(ctx: _Ctx, profile_slug: str) -> None:
    """Update an article and verify the resulting history."""
    print("\nUpdate + edit history:")
    _check(
        ctx,
        f"PUT /articles/{profile_slug}",
        ctx.contrib.put(
            f"/articles/{profile_slug}",
            json={"content": "# Smokescreen\n\nUpdated biography."},
        ),
        200,
    )
    _check(
        ctx,
        f"GET /articles/{profile_slug}/history (JSON)",
        ctx.anon.get(f"/articles/{profile_slug}/history"),
        200,
    )
    _check(
        ctx,
        f"GET /articles/{profile_slug}/history/view (HTML)",
        ctx.anon.get(f"/articles/{profile_slug}/history/view"),
        200,
    )


def _check_moderation(ctx: _Ctx, profile_slug: str) -> None:
    """Submit for review, inspect the queue, and approve."""
    print("\nModeration workflow:")
    _check(
        ctx,
        "POST submit (draft → pending)",
        ctx.contrib.post(f"/moderation/{profile_slug}/submit"),
        200,
    )
    _check(ctx, "GET /moderation/queue (JSON)", ctx.mod.get("/moderation/queue"), 200)
    _check(
        ctx,
        "GET /moderation/queue/view (HTML)",
        ctx.mod.get("/moderation/queue/view"),
        200,
    )
    _check(
        ctx,
        "POST approve (pending → published)",
        ctx.mod.post(f"/moderation/{profile_slug}/approve"),
        200,
    )


def _check_post_publish(ctx: _Ctx, profile_slug: str) -> None:
    """Check tag browsing, full-text search, and contributor profile."""
    print("\nPost-publish:")
    _check(ctx, "GET /tags", ctx.anon.get("/tags"), 200)
    _check(ctx, "GET /tags/smoke-test", ctx.anon.get("/tags/smoke-test"), 200)
    _check(
        ctx,
        f"GET /contributors/{_CONTRIB_USERNAME}",
        ctx.anon.get(f"/contributors/{_CONTRIB_USERNAME}"),
        200,
    )
    _check(
        ctx,
        "GET /articles/search/results?q=smokescreen",
        ctx.anon.get("/articles/search/results", params={"q": "smokescreen"}),
        200,
    )


def _check_engagement(ctx: _Ctx, profile_slug: str) -> None:
    """Check voting and comment flows."""
    print("\nVotes:")
    _check(
        ctx,
        f"PUT /votes/{profile_slug} +1",
        ctx.contrib.put(f"/votes/{profile_slug}", json={"value": 1}),
        200,
    )
    _check(
        ctx,
        f"GET /votes/{profile_slug}",
        ctx.anon.get(f"/votes/{profile_slug}"),
        200,
    )
    _check(
        ctx,
        f"DELETE /votes/{profile_slug}",
        ctx.contrib.delete(f"/votes/{profile_slug}"),
        204,
    )

    print("\nComments:")
    r = ctx.contrib.post(
        f"/comments/{profile_slug}", json={"body": "Great smoke work!"}
    )
    _check(ctx, f"POST /comments/{profile_slug}", r, 201)
    _check(
        ctx,
        f"GET /comments/{profile_slug}",
        ctx.anon.get(f"/comments/{profile_slug}"),
        200,
    )
    if r.status_code == 201:
        cid = r.json()["id"]
        _check(
            ctx,
            f"PUT /comments/{profile_slug}/{cid}",
            ctx.contrib.put(
                f"/comments/{profile_slug}/{cid}", json={"body": "Edited!"}
            ),
            200,
        )
        _check(
            ctx,
            f"DELETE /comments/{profile_slug}/{cid}",
            ctx.contrib.delete(f"/comments/{profile_slug}/{cid}"),
            204,
        )


def _check_auth_guards(ctx: _Ctx) -> None:
    """Spot-check that auth and role enforcement are working."""
    print("\nAuth guards:")
    _check(
        ctx,
        "anon → /moderation/queue → 401",
        ctx.anon.get("/moderation/queue"),
        401,
    )
    _check(
        ctx,
        "contributor → /moderation/queue → 403",
        ctx.contrib.get("/moderation/queue"),
        403,
    )


def _check_auth_endpoints(ctx: _Ctx) -> None:
    """Check OAuth login redirect, bad-code handling, and logout.

    The bad-code check contacts GitHub's token endpoint; requires internet access. Run
    last — logout clears the contrib client's session cookie.
    """
    print("\nAuth endpoints:")
    _check(
        ctx,
        "GET /auth/login → 307 to GitHub",
        ctx.anon.get("/auth/login", follow_redirects=False),
        307,
    )
    _check(
        ctx,
        "GET /auth/callback?code=bogus → graceful redirect (not 500)",
        ctx.anon.get(
            "/auth/callback", params={"code": "bogus"}, follow_redirects=False
        ),
        307,
    )
    _check(
        ctx,
        "GET /auth/logout → 307",
        ctx.contrib.get("/auth/logout", follow_redirects=False),
        307,
    )


# ── Runner ─────────────────────────────────────────────────────────────────────


def _run_suite(base: str, contrib_id: int, mod_id: int) -> list[str]:
    """Open HTTP clients, run all check groups, return failure labels."""
    ctx = _Ctx(
        contrib=httpx.Client(
            base_url=base, cookies={"session": _cookie(contrib_id, "contributor")}
        ),
        mod=httpx.Client(
            base_url=base, cookies={"session": _cookie(mod_id, "moderator")}
        ),
        anon=httpx.Client(base_url=base),
    )
    try:
        _check_static(ctx)
        profile_slug = _create_articles(ctx)
        if profile_slug:
            _check_article_read(ctx, profile_slug)
            _check_article_update(ctx, profile_slug)
            _check_moderation(ctx, profile_slug)
            _check_post_publish(ctx, profile_slug)
            _check_engagement(ctx, profile_slug)
        _check_auth_guards(ctx)
        _check_auth_endpoints(ctx)
    finally:
        ctx.contrib.close()
        ctx.mod.close()
        ctx.anon.close()
    return ctx.failures


def main() -> None:
    """Run the smoke test suite against a live local server."""
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--base-url", default="http://localhost:8000")
    args = parser.parse_args()
    base = args.base_url.rstrip("/")

    try:
        httpx.get(f"{base}/", timeout=3)
    except httpx.ConnectError:
        sys.exit(f"Cannot reach {base} — is uvicorn running?")

    print(f"\nTarget: {base}\n")

    conn = psycopg.connect(_psycopg_url())
    contrib_id = mod_id = None
    try:
        _pre_cleanup(conn)
        contrib_id, mod_id = _seed_users(conn)
        print(f"Seeded: contributor id={contrib_id}  moderator id={mod_id}\n")
        failures = _run_suite(base, contrib_id, mod_id)
    finally:
        print("\nCleaning up smoke-test data...")
        _delete_smoke_data(conn, contrib_id, mod_id)
        conn.close()
        print("  ✓ done")

    n = len(failures)
    print(f"\n{'All checks passed.' if n == 0 else f'{n} check(s) failed.'}\n")
    sys.exit(0 if n == 0 else 1)


if __name__ == "__main__":
    main()
