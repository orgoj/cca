# Reach as an optional CCA terminal backend

Status: idea only, deferred by the user on 2026-09-30. Do not implement now.
The preferred next experiment is Dippy as a cca-tmux-cli backend; the user
reports its `run` and `run-on-server` subcommands. That interface has not yet
been inspected. The assessment below is retained only as background for a
possible later Reach backend, not as an active implementation plan.

Assessed 2026-09-30 by source inspection only. Local checkout:
`/home/michael/projects/Reach`, commit
`946904bec7f052c2b3e9071d02732aefabc084a9`, Cargo version 0.7.0.
No application launch, build, MCP connection, SSH access, or remote command
execution was performed. These are implementation observations, not runtime
compatibility results. Keep this machine-specific assessment in the private
agent bundle, not the public CCA tree.

## Conclusion

Reach is promising for a human and AI operating the same visible SSH terminal.
Its existing external control interface is MCP over loopback HTTP. A CLI
client can call that interface without an AI model, so terminal-based callers
are feasible even though the session owner remains a desktop application.
An optional backend is plausible; a complete replacement for cca-tmux-cli is
not ready from the current API alone.

Windows support is a real advantage: native Rust SSH and desktop local PTY
support avoid needing tmux for the Reach session. The user reports that most
colleagues now use Linux or macOS, so Windows is a useful bonus rather than
the main reason to migrate. A Windows CLI wrapper would also need a suitable
implementation/runtime; selecting Reach does not make the current Bash-based
cca-tmux-cli native on Windows.

## Existing control surface

- `src-tauri/src/main.rs` calls `reach_lib::run()`; the inspected entrypoint
  starts Tauri. Cargo declares no separate CLI binary or headless feature.
  The single-instance handler in `lib.rs` ignores launch arguments and focuses
  the window. No standalone session-management CLI is established by these
  entrypoints. GUI-owned sessions and consent remain required.
- `mcp/server.rs`: POST JSON-RPC to `http://127.0.0.1:<port>/mcp`, authenticated
  with a bearer token. `/health` and GET `/mcp` provide a non-secret probe.
  This is plain request/response HTTP; a small CLI could implement the needed
  MCP initialize and tool calls. It need not spawn Reach or run an AI client.
- `mcp/tools.rs`: four tools: `list_sessions`, `describe_session`,
  `read_output`, `send_input`. Only explicitly shared SSH/local sessions are
  available. No exposed create/connect/share session tool, recipe execution
  tool, raw-key/cancel tool, output cursor, or completed-command API in this
  tool definition set.
- `ipc/mcp_commands.rs`: enabling, sharing, selecting agent/mode, and confirming
  happen through Tauri IPC. Settings/token can persist, but session sharing
  deliberately does not survive restart. CLI callers cannot create that
  authorization through MCP.
- Recipes build parameterized Bash heredocs via `recipe/invoke.rs` and
  `ipc/recipe_commands.rs`; preparation returns the command to the frontend
  for terminal input. Recipes are not an alternative external CLI/MCP API in
  the inspected tool set.

## Compatibility gaps

- `send_input` adds a newline and returns `status: sent`. It does not wait for
  completion or report the remote exit code. CCA currently wraps commands with
  unique START/END markers, preserves exit/signal status, polls with a timeout,
  and runs literal multiline Bash programs (`bin/cca-tmux-cli`, run section).
  A Reach adapter would need equivalent completion semantics.
- MCP retains a rolling 64 KiB byte buffer per shared session
  (`mcp/session.rs`). `read_output` returns a tail, default 120 and maximum
  500 lines (`mcp/tools.rs`), with best-effort secret redaction. There is no
  cursor/pagination in this tool schema, and the actual read result does not
  explicitly flag buffer truncation. Polling cannot guarantee complete output
  if a command emits a burst larger than these limits. Lost START/END markers
  must be an error, never a successful empty result. Reliable full output
  needs an upstream output/completion facility or deliberate capture design.
- Inputs are limited to 2048 bytes and at most 12 writes/minute by the baseline
  (`mcp/guard.rs`), with potentially stricter agent policies. A marker wrapper
  consumes that size budget; large `--script` calls need a different mechanism.
  Encoding scripts to hide their contents from command analysis would undermine
  Reach's review model and is not an acceptable integration shortcut.
- Describe/read-before-write, rationale, secret checks, danger/policy checks,
  and read freshness can refuse input. Modes are Ask, AutoSafe, Auto, Dangerous;
  automatic approval only changes human prompting, not the baseline guards.
  CCA must surface refusals and request metadata honestly.
- Password-prompt detection and outgoing secret redaction are heuristic, as
  documented in `mcp/session.rs` and `mcp/redact.rs`. README safety claims should
  not be treated as guarantees. In the inspected write path, guards run before
  awaiting confirmation; it does not revalidate all session facts afterward.
- `McpState::handle` currently uses the same `default` client key for all calls.
  Multiple wrappers/agents share precondition bookkeeping. An adapter should
  serialize its own command execution, but external clients/human input still
  require coordination; this is not isolated concurrent job execution.

## Suggested future direction (not implemented)

Preserve tmux as the default and consider an explicitly selected Reach backend.
Map `list` to shared session discovery and `read` to output retrieval; map
configured server aliases to unique session IDs and fail on ambiguity. Keep
endpoint/token references and server mapping in caller project configuration,
never in the shared toolkit or relative to the installed script.

Start a future proof of concept with short, low-output commands and verify
completion markers, nonzero exits, interruptions, stale reads, consent refusal,
restart/unsharing, and output overflow. Exposing reviewed script execution,
job IDs/status, complete output retrieval, cancellation, and CLI-controlled
session lifecycle upstream would make the backend substantially more useful.

Use secure credential handling for authenticated HTTP; CCA's existing API-auth
convention is `cca-curl-secret`. A cross-platform wrapper needs a conscious
choice of supported runtime and credential integration, not an assumption that
Bash and its dependencies exist on stock Windows.

A truly headless Reach would be a larger upstream change: the current sender
and consent callbacks use Tauri AppHandle/AppState, and SSH/vault/host-key
interaction would need lifecycle and non-GUI consent handling. The library
crate alone does not establish a supported headless service.

Local README and LICENSE say MIT, while Cargo.toml still says
`LicenseRef-Reach-SAL`; metadata is inconsistent. Before copying/extracting
backend code, resolve that inconsistency. Calling the existing interface avoids
the immediate need to extract its implementation.
