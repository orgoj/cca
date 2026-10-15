---
name: cca
description: The `cca` command (Cyber-CLI Admin) for server administration in a project with a .cca.toml. Use before running any cca subcommand, when setting up or checking a project's cca configuration, or when installing cca skills.
---

# cca

One command, `cca <subcommand>`. Project settings come only from the nearest `.cca.toml`
(found from the current directory upwards); secrets only from the project's sops files.
`cca --help` and `cca <subcommand> --help` are authoritative; this skill says when to use
what.

| Subcommand | Use it to | Reference |
|---|---|---|
| `cca config show` | see which `.cca.toml` is used and its values with defaults | [config](references/config.md) |
| `cca doctor` | check that the project is ready for cca | [doctor](references/doctor.md) |
| `cca install skills` | link the cca skills into an agent skill directory | [install](references/install.md) |

Rules:

- Run cca from the project directory (or below it); never pass secrets on the command line.
- Exit code 2 means a usage or configuration error; the message names the file and key.
- `cca --version` prints the installed release.
