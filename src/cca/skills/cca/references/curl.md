# cca curl

Runs curl with a credential from the project's sops file (`[secrets] curl` in
`.cca.toml`). The credential never appears in argv or in the output.

```
cca curl [--cred-id ID] [CURL-OPTION...] URL
```

- Exactly one URL, `https://` only (positional or `--url`). The credential is the one
  whose `origins` contain the URL's origin; `--cred-id ID` picks one when several match.
  No match → exit 2 listing the credential ids.
- `{TOKEN}` in the URL or in an option value is replaced by the bearer token (APIs with
  the token in the path), e.g. `cca curl -sf 'https://api.example.com/v1/{TOKEN}/list'`.
- Every curl option works as in curl, except `-L`/`--location`, `--location-trusted`,
  `-K`/`--config`, `--expand-config` and `--expand-url` (exit 2). Follow a redirect by calling the new URL
  yourself. Request data cannot come from stdin (`-d @-`); use `-d @FILE`.
- Secrets in curl stdout and stderr (`-v`, `-w`, error messages) and in files written by
  `--trace`, `--trace-ascii`, `--libcurl`, `--stderr`, `-D` and `-w '%output{FILE}'`
  show as `[REDACTED]`. `-o FILE` is written unchanged.
- Exit code is curl's; 2 also means a usage or configuration error found before curl ran.

Example: `cca curl --cred-id example_api -s -f -o tmp/status.json https://api.example.com/v1/status`
