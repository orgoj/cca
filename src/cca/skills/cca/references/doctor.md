# cca doctor

Checks the current project directory and prints one line per check (`OK`, `WARN`,
`FAIL`); exits 1 when any check fails.

Checks: `.cca.toml` found and valid, `sops` on PATH, the project directories
`cca/guides` and `cca/incidents`, the `[run.log]` directory when logging is configured, the `backlog` CLI and the
project statuses `Note` and `Done` (used by `cca watchlist`),
the `cca` skill links in `.claude/skills`, and that no old `cca-*` script or skill is
installed: an agent skill dir or `PATH` dir that is an old CCA checkout's `bin/` or
`skills/` (directly or through a link), or a link in it into those, fails in the
project's skill dirs and warns in user-level skill dirs (`~/.claude/skills`, ...) and
`PATH` dirs. Remove them by hand; doctor only reads link metadata.

`cca doctor --fix` removes broken skill links that `cca install skills` created
(recorded in `.claude/skills/.cca-skills.json`); it never touches other links or files.
