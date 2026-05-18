{ config, lib, pkgs, ... }:

with lib;
let
  meta = import ./meta.nix;
  cfg  = config.services.${meta.slug};
in {
  options.services.${meta.slug} = {
    enable = mkEnableOption meta.displayName;

    package = mkOption {
      type = types.package;
      description = "The ${meta.slug} package (built via uv2nix).";
    };

    domain = mkOption {
      type = types.str;
      description = "Public domain name for TLS and Caddy virtual host.";
    };

    port = mkOption {
      type = types.port;
      default = 8000;
      description = "Port uvicorn listens on (loopback only; Caddy proxies it).";
    };

    dbName = mkOption {
      type = types.str;
      default = meta.slug;
      description = "PostgreSQL database name.";
    };

    environmentFile = mkOption {
      type = types.nullOr types.path;
      default = null;
      description = ''
        Path to a file containing secret environment variables
        (GITHUB_CLIENT_ID, GITHUB_CLIENT_SECRET, SESSION_SECRET, …).
        Loaded by systemd before the process starts.
      '';
    };
  };

  config = mkIf cfg.enable {
    users.users.${meta.slug} = {
      isSystemUser = true;
      group = meta.slug;
      description = "${meta.displayName} service user";
    };
    users.groups.${meta.slug} = {};

    systemd.services.${meta.slug} = {
      description = "${meta.displayName} (uvicorn)";
      after = [ "network.target" "postgresql.service" ];
      requires = [ "postgresql.service" ];
      wantedBy = [ "multi-user.target" ];

      environment = {
        DATABASE_URL = "postgresql:///${cfg.dbName}";
        UVICORN_HOST = "127.0.0.1";
        UVICORN_PORT = toString cfg.port;
      };

      serviceConfig = {
        ExecStart = "${cfg.package}/bin/uvicorn ${meta.pyModule}.main:app --host 127.0.0.1 --port ${toString cfg.port}";
        Restart = "on-failure";
        RestartSec = "5s";
        User = meta.slug;
        Group = meta.slug;
        EnvironmentFile = mkIf (cfg.environmentFile != null) cfg.environmentFile;

        # Hardening
        NoNewPrivileges = true;
        ProtectSystem = "strict";
        ProtectHome = true;
        PrivateTmp = true;
        PrivateDevices = true;
        ProtectKernelTunables = true;
        ProtectControlGroups = true;
        RestrictAddressFamilies = [ "AF_INET" "AF_INET6" "AF_UNIX" ];
        RestrictNamespaces = true;
        LockPersonality = true;
        MemoryDenyWriteExecute = true;
      };
    };
  };
}
