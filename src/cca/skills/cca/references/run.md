# cca run

Run a command on a server of the project's `[servers]`.

```
cca run [--timeout SEC] SERVER [-- CMD...]
cca run [--timeout SEC] --all [-- CMD...]
cca run [--timeout SEC] --create-file PATH SERVER < FILE
cca run --list
cca run --read [--lines N | --marker M | --scrollback] SERVER
cca run --session [SERVER...]
```

- Options go only before SERVER; the command goes after `--` or on stdin. Several words
  after `--` are joined with spaces, as ssh does: quote a pipeline as one argument
  (`cca run server1 -- 'ps aux | grep nginx'`).
- Multiline scripts: a quoted heredoc on stdin, nothing after SERVER:

  ```
  cca run server1 <<'EOF'
  df -h /
  systemctl is-active nginx
  EOF
  ```
- The remote command runs with bash, its stdin is `/dev/null`: no interactive prompts,
  use non-interactive flags (`apt-get -y`, `systemctl --no-pager`).
- Output is stdout and stderr together, printed when the command finishes.
- Transport from `run.transport`: `tmux` (default) types the command into a visible ssh
  window per server in session `run.tmux.session`, so the user sees it and can press
  Ctrl-C; `ssh` runs it directly. `--read` and `--session` exist only for tmux.
- `--create-file` writes stdin to the absolute remote PATH atomically (temp file in the
  same directory, then `mv`); an existing file keeps its mode. Over tmux at most 64 KiB.
- `--all` runs on every server in config order, each output in
  `<server-result name="..." exit="...">`, and stops at the first failure.
- `--list` prints `NAME<TAB>SSH_TARGET`, with tmux also `window` or `-`.

Exit status: the remote command's; 124 when `--timeout` (default 300 s) passed;
130/143/129/137 when the command was interrupted, terminated, hung up or killed; 2 a
usage, config or transport error; 255 ssh could not connect.

Timeout over tmux: the command keeps running in the window. The error names its marker;
do not start another command on that server until it finished:
`cca run --read --marker CCA_... SERVER` prints its output and exits with its status,
or 124 while it still runs.

With `[run.log]` every command is appended to `<dir>/<date>-<operator>.log` with likely
secrets masked. With `run.tokf = true` the output passes through `tokf` when installed.
`cca doctor` checks transport, tmux, ssh, session and log dir.
