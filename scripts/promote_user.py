#!/usr/bin/env python3
"""Set the role of a local dev user.

Sign out and back in after running for the new role to take effect (it is cached in the
session cookie).

Usage (from project root, inside devenv shell):   uv run python scripts/promote_user.py
<github_username> <role>

Roles: contributor | moderator | admin
"""

from __future__ import annotations

import argparse
import sys

import psycopg

from superhero_project.config import settings


def _psycopg_url() -> str:
    """Strip asyncpg driver prefix so psycopg can use the URL."""
    return settings.database_url.replace("postgresql+asyncpg://", "postgresql://", 1)


def main() -> None:
    """Update a user's role in the local dev database."""
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("username", help="GitHub username of the user to update")
    parser.add_argument("role", choices=["contributor", "moderator", "admin"])
    args = parser.parse_args()

    conn = psycopg.connect(_psycopg_url())
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE users SET role = %s WHERE github_username = %s "
                "RETURNING display_name",
                (args.role, args.username),
            )
            row = cur.fetchone()
            if row is None:
                sys.exit(
                    f"User '{args.username}' not found — "
                    "have they signed in at least once?"
                )
        conn.commit()
    finally:
        conn.close()

    print(f"Updated {args.username} → {args.role}")
    print("Sign out and back in for the new role to take effect.")


if __name__ == "__main__":
    main()
