# Superhero Universe Wiki

A collaborative wiki for a shared superhero fiction universe. Contributors write and edit articles covering heroes, villains, events, organizations, locations, and lore.

Built with FastAPI, SQLAlchemy, Jinja2, GitHub OAuth, and PostgreSQL. Self-hosted on NixOS.

## Local dev

Requires [devenv](https://devenv.sh).

```sh
devenv up    # starts PostgreSQL on 127.0.0.1:5432
devenv shell # enters the dev shell with Python + uv
```

The `DATABASE_URL` environment variable is set automatically inside the shell.

## Spec

See [`spec/idea/MVP.md`](spec/idea/MVP.md) for the full design and [`spec/milestone/`](spec/milestone/) for the build plan.
