# C2: Migrate Frontend JavaScript to TypeScript
Status: in-progress

Convert all hand-written frontend JavaScript to TypeScript and add a minimal build
step. No behaviour changes — this is a type-safety and tooling improvement only.

---

- [x] **1.** `chore(frontend): add TypeScript build toolchain`
  Add `esbuild` to `devenv.nix`. Wire a devenv process that watches
  `static/ts/**/*.ts` and recompiles to `static/js/**/*.js` on change (runs via
  `devenv up -d`), plus an `enterShell` hook for the initial one-shot build on
  `devenv shell`. Add `scripts/build_js.sh` for CI and production deployments.
  Update `.gitignore` to exclude compiled output and commit source `.ts` files
  instead.
  `devenv.nix scripts/build_js.sh .gitignore`

- [x] **2.** `refactor(frontend): convert article.js to TypeScript`
  Rename `static/js/article.js` → `static/ts/article.ts`. Add types for the vote
  state object, comment API response shape, and DOM query results. Fix any type
  errors surfaced by the compiler.
  `superhero_project/static/ts/article.ts`

- [x] **3.** `refactor(frontend): convert preview.js to TypeScript`
  Rename `static/js/preview.js` → `static/ts/preview.ts` and add types.
  `superhero_project/static/ts/preview.ts`
