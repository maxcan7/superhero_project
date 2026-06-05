# C9: Continuous Integration
Status: not started

Adds a GitHub Actions workflow that runs `uv audit` on every push and pull
request to main. Establishes the CI skeleton so future jobs (tests, type
checking) have a home.

---

## Tasks

- [ ] **1.** `chore: add GitHub Actions audit workflow`
  Create `.github/workflows/audit.yml`. The workflow runs `uv audit` to catch known CVEs in the dependency tree on every push to main and on pull requests targeting main.

  ```yaml
  name: Audit

  on:
    push:
      branches: [main]
    pull_request:
      branches: [main]

  jobs:
    audit:
      runs-on: ubuntu-latest
      steps:
        - uses: actions/checkout@v4
        - uses: astral-sh/setup-uv@v5
        - run: uv audit
  ```

  No secrets or service containers needed — `uv audit` checks `uv.lock` against the OSV advisory database without installing packages.
`.github/workflows/audit.yml`
