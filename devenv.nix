{ pkgs, ... }:

{
  languages.python = {
    enable = true;
    uv.enable = true;
  };

  services.postgres = {
    enable = true;
    package = pkgs.postgresql_16;
    listen_addresses = "127.0.0.1";
    initialDatabases = [{ name = "superhero_dev"; }];
  };

  env.DATABASE_URL = "postgresql://127.0.0.1/superhero_dev";
}
