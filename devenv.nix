{ pkgs, ... }:

let
  pgPort = 5433;
  pgDb   = "superhero_dev";
  tsSrc  = "./superhero_project/static/ts";
  jsOut  = "./superhero_project/static/js";
  esbuildArgs = "${tsSrc}/article.ts ${tsSrc}/preview.ts --outdir=${jsOut} --target=es2020";
in
{
  packages = [ pkgs.esbuild ];

  languages.python = {
    enable = true;
    uv.enable = true;
  };

  # One-shot compile on `devenv shell`; the process below watches on `devenv up -d`.
  enterShell = ''
    esbuild ${esbuildArgs}
  '';

  # Rebuilds JS automatically whenever a .ts file changes during development.
  processes.esbuild.exec = "esbuild ${esbuildArgs} --watch";

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
