{ pkgs, ... }:

# NixOS system configuration for the production server.
# Deploy: nixos-rebuild switch --flake .#server --target-host user@host
# Rollback: nixos-rebuild switch --rollback

let
  meta = import ./meta.nix;
in {
  imports = [ ./module.nix ];

  # ---- App ----------------------------------------------------------------

  services.${meta.slug} = {
    enable = true;
    # package is set in the flake overlay once uv2nix packaging is wired up.
    # package = pkgs.${meta.slug};
    domain = "example.com"; # override per deployment
    port = 8000;
    dbName = meta.slug;
    environmentFile = "/run/secrets/${meta.slug}-env";
  };

  # ---- Database -----------------------------------------------------------

  services.postgresql = {
    enable = true;
    package = pkgs.postgresql_16;
    ensureDatabases = [ meta.slug ];
    ensureUsers = [{
      name = meta.slug;
      ensureDBOwnership = true;
    }];
  };

  # ---- Reverse proxy ------------------------------------------------------

  services.caddy = {
    enable = true;
    virtualHosts."example.com" = { # mirror services.${meta.slug}.domain
      extraConfig = ''
        reverse_proxy localhost:8000
      '';
    };
  };

  # ---- Backups ------------------------------------------------------------

  systemd.services."${meta.slug}-backup" = {
    description = "${meta.displayName} — pg_dump backup";
    after = [ "postgresql.service" ];
    serviceConfig = {
      Type = "oneshot";
      User = "postgres";
      ExecStart = pkgs.writeShellScript "${meta.slug}-backup" ''
        set -euo pipefail
        BACKUP_DIR=/var/backup/${meta.slug}
        mkdir -p "$BACKUP_DIR"
        TIMESTAMP=$(date +%Y%m%d_%H%M%S)
        ${pkgs.postgresql_16}/bin/pg_dump ${meta.slug} \
          > "$BACKUP_DIR/${meta.slug}_''${TIMESTAMP}.sql"
        find "$BACKUP_DIR" -name "*.sql" -mtime +30 -delete
      '';
    };
  };

  systemd.timers."${meta.slug}-backup" = {
    description = "${meta.displayName} — daily pg_dump timer";
    wantedBy = [ "timers.target" ];
    timerConfig = {
      OnCalendar = "daily";
      Persistent = true;
    };
  };
}
