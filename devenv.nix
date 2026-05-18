{ pkgs, ... }:

let
  pgPort = 5433;
  pgDb   = "superhero_dev";
in
{
  languages.python = {
    enable = true;
    uv.enable = true;
  };

  services.postgres = {
    enable = true;
    package = pkgs.postgresql_16;
    listen_addresses = "127.0.0.1";
    port = pgPort;
    initialDatabases = [{ name = pgDb; }];
  };

  dotenv.enable = true;

  env.DATABASE_URL = "postgresql://127.0.0.1:${toString pgPort}/${pgDb}";

}
