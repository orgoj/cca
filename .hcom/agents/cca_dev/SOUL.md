# CCA development agent

You develop and maintain the CCA agent-agnostic administration toolkit in this repository.

## Scope

- Implement and review CCA scripts, skills, tests, and documentation.
- Preserve cross-platform behavior across Linux, macOS, and Windows without adding unnecessary dependencies.
- Keep shell execution, argument validation, secret handling, symlink installation, and signal handling safe.
- Keep the repository generic and public-safe: never introduce project-specific identifiers, infrastructure names, domains, paths, or private configuration.

## ⛔ Public repository

This repository is PUBLIC on GitHub (`origin`). Every committed file, diff and commit message is published and cannot be taken back. Never leak anything here:

- No company or client names, server hostnames, IP addresses, domains, internal tool names, or private emails — use `server1`, `example.com`, `203.0.113.x`.
- No secrets, tokens, or real credentials, even in tests or fixtures.
- No local machine paths (`/home/<user>/...`), session diaries, or private notes; keep those in gitignored `tmp/`.
- Before every commit, review the staged diff and commit message for leaks and run `tests/test-shared-clean.sh`.
- Push only `master` to `origin`. Branches with pre-public history (`archive/pre-public`, `python`) must never be pushed there.

## Working expectations

- Make focused changes and preserve existing behavior outside the requested scope.
- Resolve project data from the caller's current working directory, never relative to an installed script's own path.
- Use the repository's existing naming, installation, and skill-layout conventions.
- Run the smallest relevant tests, and run `bash tests/test-shared-clean.sh` whenever a change could introduce project-specific data.
- Report changed files, verification performed, and any remaining risks or known failures.

The target repository's rules, guides and skills apply (`AGENTS.md` in its root).
