# cca config show

Prints the path of the loaded `.cca.toml` (first line, as a `#` comment) and the
validated document with every default filled in. It never decrypts secrets.

- Discovery: the nearest `.cca.toml` from the physical current directory upwards; a
  nested project's file shadows the parent's. `cca --config PATH config show` uses an
  explicit file instead.
- Path values in the file are relative to the file's directory.
- Unknown keys are reported as warnings on stderr and ignored; an invalid value or a
  `schema_version` newer than the installed `cca` exits 2 naming the key.

Minimal file:

```toml
schema_version = 1

[servers.server1]
ssh = "admin@server1.example.com"
```
