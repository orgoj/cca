# Records: incidents, guides, lessons

Read [knowledge](knowledge.md) first: its writing rules apply to everything here.

## Incidents

An incident is a dated, immutable record of one event or one piece of substantive work
(troubleshooting, an audit, an analysis without a failure) in
`<kb>/incidents/YYYY-MM-DD-brief-description.md`.

1. **Same event already recorded?** `tantivy2agents search "<2-4 words>"`. Append to an
   existing file only when it is the same event or its continuation (same time window and
   problem), or the same task or its continuation: add a dated section, never rewrite the
   original. Same server, service or symptom alone is not enough; a new event at another
   time is a new incident.
2. **Timeline:** run `date` for the current time, at the moment the user refers to
   something happening "now". Use verified timestamps only; a missing time is asked for or
   written as missing, never estimated.
3. **Write** with the matching template; keep only metadata and sections with verified
   content. Report the path. The index updates itself.

Rules:

- Root Cause only for a problem and only when proven; otherwise record symptom, evidence
  and `unverified — <open question>, verify with: <command/query>`.
- Duration only from verified start and end times, never from the session length.
- `Status:` is the state when written; nobody updates it later. A mitigation applied
  after the traffic ended is `monitoring`: record the deployment time and the condition
  that verifies it. Later work checks the current state and appends a dated note.
- Shape: problem = symptom → evidence → what was done → what remains open; work = task →
  verified findings → actions → outcome and open questions. No session narration.
- Event-specific evidence stays in the incident; reusable tool or product behaviour goes
  into a guide that the incident links.

Problem template (delete every heading without verified content):

```markdown
---
date: 2026-10-10
time: 14:23:15
servers: [server1]
services: [nginx]
severity: medium        # critical|high|medium|low, only when the evidence supports it
status: resolved        # resolved|monitoring|investigating
tags: [nginx, load]
---

# Incident: Brief description

**Reported:** 2026-10-10 14:23
**Status:** Resolved

## Problem Description
## Investigation        <- commands actually run and their real output
## Root Cause           <- proven only
## Solution             <- what was done, by whom
## Prevention           <- only if something concrete was decided
```

Work template: frontmatter `date`, `time`, `status: completed|in-progress`, `tags`
(servers/services only if relevant), title `# Work Record: ...`, sections `Task`,
`Verified Findings`, `Actions Taken`, `Outcome and Open Questions`. A completed audit does
not mean every finding is fixed.

## Guides

A guide is a current procedure for one topic: `<kb>/guides/<keyword>-<topic>.md`.

1. Search for an existing guide (`tantivy2agents search`, `outline`/`read`); update it
   rather than add a near-duplicate. Read natively only the guide you edit.
2. Frontmatter: `name:` starting with the keyword, `servers: [...]`, `tags: [...]`
   containing the keyword.
3. Sections, only those with verified content: Symptoms, Diagnostic steps, Solution,
   Common traps, Prevention, Related incidents (file names with one-line descriptions,
   no incident content). Headings name one topic each: agents read single sections from
   the outline.
4. **Findability:** the tool or technology keyword is in the filename, `name:` and
   `tags:`; after writing, `tantivy2agents search "<keyword>"` must return the guide first.
5. **Freshness:** on every edit update or remove what the change makes stale; live values
   may carry `(verified 2026-10-10)` inline.

- Commands in guides are the plain server command (`sudo nginx -t`) or a `cca`
  subcommand (`cca server status server1`), never wrapped in `cca run -t ... --`.
- Moving content into another guide leaves only a link at the old place.
- A server guide (`guides/servers/<name>.md`) holds type (container/VM/bare metal), OS,
  hardware, addresses, services with versions, applications, key paths, known issues.

## Lessons from a session

After a user correction, a failure or a finished task, capture what future work needs.

1. Keep only what actually happened: a lesson comes from a real failure with a real
   cause. First write `what failed → why → what fixed it` (analysis only); without the
   "why" verify the cause or drop the lesson.
2. Place it: critical rules (safety, data loss, tool misuse) in the project's rules file
   (`AGENTS.md`/`CLAUDE.md`, check which), procedures and tips in `guides/`, server facts
   in the server guide. Root cause and narrative stay in the incident.
3. Format: a one-line imperative, at most one evidence line `Error <YYYY-MM-DD>: <what happened>`;
   no quotes of the user, no session story, no rationale in the rule. Same format in agent
   bundles (`SOUL.md`, `MEMORY/`).
4. Do not regress older lessons: search the 2-5 earlier incidents/guides on the topic
   first. Different context (OS, version, service) → branch the guide; a real conflict →
   report it and wait for approval.
5. Read every edited file in full afterwards: each new rule follows the format and is at
   most about three lines. Report what changed and why.

Deduplication across guides and archiving incidents is [maintenance](maintenance.md), not
part of a session lesson.
