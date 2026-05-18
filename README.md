# Superhero Universe Wiki

A collaborative wiki for a shared superhero fiction universe. Contributors write and edit articles covering heroes, villains, events, organizations, locations, and lore.

Built with FastAPI, SQLAlchemy, Jinja2, GitHub OAuth, and PostgreSQL. Self-hosted on NixOS.

## Local dev

Requires [devenv](https://devenv.sh).

```sh
devenv up    # starts PostgreSQL (background — see DEV.md)
devenv shell # dev shell for running commands
```

See [DEV.md](DEV.md) for the full setup walkthrough, GitHub OAuth app registration,
user promotion, manual test flows, and smoke test instructions.

### Tests

```sh
uv run pytest
```

## Spec

See [`spec/idea/MVP.md`](spec/idea/MVP.md) for the full design and [`spec/milestone/`](spec/milestone/) for the build plan.
