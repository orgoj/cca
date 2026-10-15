# sops file shape fixtures

Decrypted-form documents (what `sops -d --output-type json` returns), validated against
the shapes in `backlog/docs/doc-2`. All values are dummies. An invalid fixture's error
must name the key below and must not contain any value from the file.

| File | Shape | Error names |
|---|---|---|
| `valid-curl.json` | curl | – |
| `valid-curl-shared-origin.json` | curl | – (two credentials share an origin; auto-selection must then fail, `--cred-id` picks) |
| `valid-cloudflare.json` | cloudflare | – |
| `invalid-curl-origin-bad-port.json` | curl | `credentials.example_api.origins[0]` |
| `invalid-curl-origin-userinfo.json` | curl | `credentials.example_api.origins[0]` |
| `invalid-curl-origin-leading-hyphen.json` | curl | `credentials.example_api.origins[0]` |
| `invalid-curl-origin-trailing-hyphen.json` | curl | `credentials.example_api.origins[0]` |
| `invalid-curl-http-origin.json` | curl | `credentials.example_api.origins[0]` |
| `invalid-curl-origin-path.json` | curl | `credentials.example_api.origins[0]` |
| `invalid-curl-duplicate-origin.json` | curl | `credentials.example_api.origins[1]` |
| `invalid-curl-missing-origins.json` | curl | `credentials.example_api.origins` |
| `invalid-curl-two-auth-forms.json` | curl | `credentials.example_api` |
| `invalid-curl-control-char.json` | curl | `credentials.example_api.bearer` |
| `invalid-curl-bad-id.json` | curl | `credentials.Example-API` |
| `invalid-cloudflare-missing-token.json` | cloudflare | `api_token` (and a warning for `token`) |

`valid-curl.json` keeps the terminal-dot form `https://API.example.com.:8443/`, which
must validate and normalize to (`https`, `api.example.com`, 8443).
