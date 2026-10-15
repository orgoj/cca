# cca doctor

Checks the current project directory and prints one line per check (`OK`, `WARN`,
`FAIL`); exits 1 when any check fails.

Checks: `.cca.toml` found and valid, `sops` on PATH, the project directories
`cca/guides` and `cca/incidents`, the `[run.log]` directory when logging is configured,
and the `cca` skill links in `.claude/skills`.

`cca doctor --fix` removes broken skill links that `cca install skills` created
(recorded in `.claude/skills/.cca-skills.json`); it never touches other links or files.
