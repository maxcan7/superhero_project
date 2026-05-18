# M8: Packaging
Status: not started

Wire uv2nix into the flake so the app can be built as a Nix package and
deployed with `nixos-rebuild switch --flake .#server`.

---

- [ ] **1.** `chore: add uv2nix input and build package in flake.nix`
  Add uv2nix as a flake input. Use it to build the app as a derivation and
  expose it as `packages.${system}.default`. The package should produce a
  working `superhero-project` binary (or equivalent entry point) from
  `uv.lock`.
  `flake.nix uv.lock pyproject.toml`

- [ ] **2.** `chore: wire package into server.nix`
  Uncomment `package = pkgs.${meta.slug};` in `nix/server.nix` and point it
  at the uv2nix-built derivation via a flake overlay or direct reference.
  Confirm `nixos-rebuild build --flake .#server` completes without errors.
  `nix/server.nix flake.nix`

- [ ] **3.** `chore: verify end-to-end deployment`
  Deploy to a test target (or dry-run with `--target-host`) to confirm the
  systemd unit starts, Caddy proxies correctly, and the app connects to
  PostgreSQL from the Nix-packaged binary. Update `nix/server.nix` domain
  placeholder with the real production domain.
  `nix/server.nix nix/module.nix`
