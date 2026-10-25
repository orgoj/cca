# cca doctor

Checks the current project directory and prints one line per check (`OK`, `WARN`,
`FAIL`); exits 1 when any check fails.

Checks: `.cca.toml` found and valid, `sops` on PATH, the age key sops will use (below), the project directories
`cca/guides` and `cca/incidents`, what `cca run` needs (servers configured,
`run.transport`, `ssh` and with tmux also `tmux` on PATH and `run.tmux.session`, `tokf`
when `run.tokf` is set), the `[run.log]` directory when logging is configured, the `backlog` CLI and the
project statuses `Note` and `Done` (used by `cca watchlist`),
the `cca` skill links in `.claude/skills`, and that no old `cca-*` script or skill is
installed: an agent skill dir or `PATH` dir that is an old CCA checkout's `bin/` or
`skills/` (directly or through a link), or a link in it into those, fails in the
project's skill dirs and warns in user-level skill dirs (`~/.claude/skills`, ...) and
`PATH` dirs. Remove them by hand; doctor only reads link metadata.

Age key: sops runs with the caller's environment, so it finds the key through
`SOPS_AGE_KEY_FILE` (an absolute path, set in the agent's launch environment), or
`SOPS_AGE_KEY` / `SOPS_AGE_KEY_CMD`, or the sops default `~/.config/sops/age/keys.txt`.
sops ignores `.sopsrc`. The check prints paths only, never a key: `OK` for a readable
absolute `SOPS_AGE_KEY_FILE`, a set `SOPS_AGE_KEY`/`SOPS_AGE_KEY_CMD` or the default file;
`WARN` for a relative path (resolved from the current directory, so it breaks in
subdirectories) or no key while the project has no secrets file; `FAIL` for an unreadable
`SOPS_AGE_KEY_FILE`, or no key while a `[secrets]` file exists. Without a key sops exits
128 and the command reports "cannot decrypt". This is diagnostics only: no setting is
read from the environment.

`cca doctor --fix` removes broken skill links that `cca install skills` created
(recorded in `.claude/skills/.cca-skills.json`); it never touches other links or files.
