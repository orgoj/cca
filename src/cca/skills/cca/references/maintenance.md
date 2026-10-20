# Maintenance: monthly upkeep of guides, incidents and the register

Monthly, or after a series of similar incidents. Read [knowledge](knowledge.md) and the
guide rules in [records](records.md) first; they apply to every operation.

**Approval first.** Every operation first reports its findings, one line each: what,
where, and the exact proposed change (guide merge, new guide, link, incident chain,
archive move, Backlog task merge or close, `area:` rename). Nothing in guides, incidents
or `backlog/` changes before the user approves; apply only the approved lines. Reversing
an existing decision needs evidence and approval, never your own judgement.

## Evidence

Save `tantivy2agents usage --since 30d --format json` to a file in the project `tmp/` and
inspect it with `yq`. It counts only reads through `tantivy2agents`, so it is a signal to
check, not proof:

- zero-result queries, searches without a read → gaps
- returned but not read, outline without read, low read-through at rank 1 → title,
  frontmatter or headings do not match the content
- never returned → archive, merge or findability candidates
- most-read sections → keep them; trim what nobody reads

## Operations

- **Gaps:** cluster incidents by frontmatter `tags:`, `servers:`, `services:` and by
  `tantivy2agents search` on the recurring symptom (not by filename or date); two or more
  incidents with the same root cause and no guide covering it are a gap.
- **Improvements:** compare guides with recent incidents for missing information. Stale
  audit by git (`git log -1 --format=%cs -- <guide>`, never a changelog in the guide): a
  guide unchanged for about 6 months whose topic overlaps a newer guide is compared with
  it and recent incidents; when it contradicts them, propose rewriting it as a thin router
  to the current guides or folding it in.
- **Duplicates:** before a merge, list the lines only in the guide being removed and check
  each is in the target; the old file stays as a thin router to the target.
- **Links:** related guides that should reference each other.
- **Prune:** unverified claims, speculative causes, duplicated rules and padding are
  findings too.

## Consolidate incidents

Recurring incidents with the same root cause dilute search. Consolidation moves the
knowledge into guides and chains the records; incidents are never deleted.

1. **Cluster:** find every incident of the problem (several search phrasings, `tags:`,
   title keywords), sorted by date. A cluster is two or more with the same root cause.
2. **Head:** the newest incident stays active. Add a section listing every earlier
   occurrence, newest first, by file name only (never with `archive/YYYY/` or the
   incidents path):
   ```markdown
   ## Earlier occurrences (same problem)
   - 2026-04-17 — 2026-04-17-server1-outage-scraper.md — blocked the source range
   - 2025-10-03 — 2025-10-03-server1-scraper.md — first occurrence
   ```
3. **Guides first (required output):** the playbook guide (`*-outage-patterns`,
   `*-troubleshooting`) gets symptom → cause → fix for the cluster; diagnostic steps,
   queries and decisions missing from topic guides go where they belong. A consolidation
   without any guide change means everything was already there: say so explicitly.
4. **Report and wait for approval:** head, chain, files to archive, guide changes.
5. **Archive** the older members: first move any chain an archived member carries into
   the head's chain, then `git mv <incident> <kb>/incidents/archive/YYYY/` (year of
   the incident). Cross-references elsewhere stay as they are: the file name is unique and
   does not change.
6. **Reindex:** `tantivy2agents index` (`git mv` does not trigger the edit hook).
7. **Verify** after the whole approved batch: every archived incident is linked from an
   active head or guide (a link from another archived file does not count); each cluster
   has exactly one active head; no link contains `archive/YYYY/` or the incidents path.

## Register cleanup (Backlog.md)

The register holds operational work, not every idea; keep the open set small enough that
related work is scheduled as one intervention.

1. `date`, then `backlog task list --plain` (open statuses) and
   `cca watchlist notes --expired`; for detail `backlog task view ID --plain`. Check items against their refs,
   incident and guide state and git history; never infer completion from age.
2. **Merge** only tasks finished by one intervention: same incident or change, same
   `window:`, same primary or tightly coupled files. Similar wording or a shared `area:`
   is not enough.
3. **Close** (`Done`, then archive) when the work is demonstrably complete, the incident
   is resolved with no follow-up, or the task lost its purpose; record the evidence.
   Expired notes are closed the same way. Never delete a task file: Done and archive keep
   the history.
4. **Normalize `area:`** variants of one subsystem (case, punctuation, abbreviations, old
   names) to one existing clear value; distinct scopes stay distinct.
5. Report one line per change (IDs, evidence, action; for a merge the surviving task and
   the refs, plan and acceptance criteria it keeps; for a rename `old → new` with every
   ID), wait for approval, then apply only with `backlog task edit` (`--add-ref`,
   `--append-notes`, `--add-label`/`--remove-label`, `-s Done`) and `backlog task archive`.
6. Verify: one survivor per merged group, no lost refs or plans, closed tasks are Done,
   no alias of a normalized `area:` remains; report counts before and after and anything
   left unchanged because it was ambiguous.
