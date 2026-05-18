# Superhero Universe Wiki

A collaborative wiki for a shared superhero fiction universe. Contributors write and edit articles covering heroes, villains, events, organizations, locations, and lore.

Built with FastAPI, SQLAlchemy, Jinja2, GitHub OAuth, and PostgreSQL. Self-hosted on NixOS.

## Local dev

Requires [devenv](https://devenv.sh) — a Nix-based tool that pins and provisions
the full dev environment (PostgreSQL 16, Python, esbuild, TypeScript) in a
reproducible shell. Install it by following the [devenv getting-started guide](https://devenv.sh/getting-started/),
then run:

```sh
devenv up    # starts PostgreSQL + esbuild watch (background — see DEV.md)
devenv shell # enter the dev shell for running commands
```

`devenv shell` also runs a one-shot JS build on entry, so compiled JS is always
present before the server starts. You do not need Node, npm, or a separate
package manager — esbuild and `tsc` are provided by devenv.

See [DEV.md](DEV.md) for the full setup walkthrough, GitHub OAuth app registration,
user promotion, manual test flows, and smoke test instructions.

### Tests

```sh
uv run pytest
```

## Spec

See [`spec/idea/MVP.md`](spec/idea/MVP.md) for the full design and [`spec/milestone/`](spec/milestone/) for the build plan.
