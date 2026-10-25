---
id: TASK-13
title: 'cca cloudflare dns compare: zone file / old NS vs Cloudflare zone'
status: Idea
assignee: []
created_date: '2026-10-25 21:48'
labels: []
dependencies: []
priority: low
type: enhancement
ordinal: 35000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Proposed subcommand: `cca cloudflare dns compare ZONE --zone-file F [--ns OLD_NS]`. Compare every name/type of a BIND zone file (or the records served by the old authoritative NS) with the Cloudflare zone, e.g. before/after a DNS migration. A/AAAA queried on a name that is a CNAME must not be reported as a false DIFF (Cloudflare answers NODATA there). Source: a consumer project's session review (finding I1). Suggested direction: reuse the existing Cloudflare subcommand and config; scope of record types, output format and exit codes still open. Needs analysis before implementation.
<!-- SECTION:DESCRIPTION:END -->
