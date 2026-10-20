# Knowledge: writing rules and search

The project's knowledge lives in `<kb>/guides/` (procedures, one file per topic,
server guides in `guides/servers/<name>.md`) and `<kb>/incidents/` (dated records).
`<kb>` is the project directory or its `cca/` subdirectory: check where the
existing files are, never create a second tree.

## Written knowledge: evidence and length

The single rule for every written artifact: guides, incidents, Backlog tasks, reports and
answers in chat. A record is acted on for years; an unchecked plausible sentence is worse
than a missing one.

- Write what you **observed** (command output, log line, file content, the user's
  statement), kept apart from what you conclude from it.
- Every number, timestamp, version, path, hostname and limit comes from a command you ran
  or a file you read. Never estimate, reconstruct from memory or round an unmeasured value.
- No invented metrics: no "confidence 85 %", "match 95 %" or severity score. State the
  concrete overlap instead ("same service, same symptom").
- Unverified content only when labelled and actionable: `unverified` (or the project's
  word, e.g. `neovereno`) plus the exact command or query that verifies it. Anything an
  existing text labels `unverified`/`assumed`/`probably` is a task, not a fact.
- Record what someone said as they said it; mark your inference as inference.
- Contradicting an existing entry needs evidence: read the current text first, report the
  conflict and wait for the user's approval before changing a decision someone made.
- Answer only from data you retrieved; when a command failed or returned nothing usable,
  say what is missing.
- Never write secrets: no passwords, tokens, keys, connection strings or cookies in a
  guide, incident, task or report; name the secret's location (`secrets/curl.secret.yaml`,
  credential id) instead.
- Short: cover the substance, then stop; no empty or speculative template sections, no
  intro restating the summary. Each command, path and rule exists once, where it belongs;
  moving it leaves a link (`→ guides/x.md`), never a shortened copy. Show the command and
  its real output instead of prose explaining it. No dated changelog in a guide: history
  is in git, the guide reads as current as a whole.

## Search: `tantivy2agents`

Topic search in guides and incidents goes through `tantivy2agents`, never through Glob or
grep. An incident whose date you know is found by listing: `ls <kb>/incidents/ | grep 2026-10-15`.

```
tantivy2agents search "nginx ssl error"            # guides and incidents, ranked
tantivy2agents search "disk full incident" --limit 5
tantivy2agents outline REF                          # headings with slugs and line ranges
tantivy2agents read REF [--section SLUG] [--lines A-B] [--numbers]
```

- 2-4 words, **one concept per query**; a mix of symptom + service + tool sinks the right
  guide. Several topics = several short searches. Include the server name when relevant.
- Each result has a `REF:` (e.g. `a3f2c1:2`); pass it to `outline`/`read` instead of the
  path. Long guide: `outline`, then `read --section`. Read indexed documents through
  `tantivy2agents read` (also a path you know: `tantivy2agents read cca/guides/x.md`):
  those reads feed the usage stats. A file you are about to edit is read with the editor's
  native tool.
- Run the first search sequentially when index readiness is unknown; an empty result is
  retried once before you conclude there is no match. No results: broaden; too many:
  refine or `--limit`.
- Follow only the cross-references the task needs. A guide describes intent, not
  necessarily today's state: open the real file before you change it or repeat a claim
  as fact.
- Archived incidents (`<kb>/incidents/archive/YYYY/`) are excluded from the index on
  purpose and keep their unique dated name: a missing `incidents/2025-10-03-x.md` is at
  `ls <kb>/incidents/archive/*/2025-10-03-x.md` (or `git log --all --full-history -- '**/2025-10-03-x.md'`).
- Usage stats: `tantivy2agents usage --since 30d [--format json]` (read-through per rank,
  zero-result queries, returned-but-unread and never-returned documents, most-read
  sections); native reads are invisible to it. Scripted searches: `TANTIVY2AGENTS_USAGE=0`.

Index: `tantivy2agents install` (once per project) registers an agent edit hook that marks
the index outdated; the next `search` rebuilds it, so no manual rebuild is needed. Edits
made outside that hook (`git mv`, another CLI, an editor) are not seen: check with
`tantivy2agents status` and run `tantivy2agents index` when the change must be searchable
now. Hook lost (settings file replaced): `tantivy2agents install --no-config`, then
`tantivy2agents index`. `index --force` only for troubleshooting. The archive is excluded
by an entry in `.tantivy2agents.json` `index_dirs`:
`{ "path": "cca/incidents/archive", "exclude": true }` (path as in the project).
