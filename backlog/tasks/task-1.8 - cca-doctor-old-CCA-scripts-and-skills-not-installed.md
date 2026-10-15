---
id: TASK-1.8
title: 'cca doctor: old CCA scripts and skills not installed'
status: Done
assignee:
  - '@cca_dev'
created_date: '2026-10-15 07:35'
updated_date: '2026-10-15 12:30'
labels: []
dependencies:
  - TASK-1.1
parent_task_id: TASK-1
priority: medium
type: feature
ordinal: 20000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Old cca-* scripts and root skills are removed once every consumer project is converted. cca doctor (needs .cca.toml, checks the new state) also checks that no agent skill dir or PATH dir is, or links into, an old CCA tree's bin/ or root skills/. Converting project scripts, docs and agent instructions is a one-time manual task (TASK-4), not a doctor check.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 User-level skill dirs from doc-2 and every PATH dir are checked the same way and reported as WARN, since they stay shared until every consumer is converted
- [x] #2 The [legacy] config table and doctor --legacy are removed from doc-1, doc-2, config, fixtures and dependent tasks
- [x] #3 The cca skill doctor reference and README describe the check
- [x] #4 No file is opened and nothing inside an old tree is listed (entries are never descended into); tests cover an untracked/gitignored .claude/skills link, a dangling link, a linked skill dir, a PATH dir, a user-level dir and unrelated links (no finding)
- [x] #5 Checks link metadata only (lstat, realpath) of the doc-2 project skill dirs, each dir and its symlink entries, and fails on a dir or link resolving into an old CCA tree's bin/ or root skills/ (dangling links and linked ancestors included); an unlistable project dir fails
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Rescoped by user decision: no doctor --legacy and no project content scan; consumer projects are converted once by hand (new TASK-4, after the complete cca is approved), TASK-2 depends on it. cca doctor (config required) now checks the doc-2 project skill dirs (FAIL), user-level skill dirs and PATH dirs (WARN, shared until all consumers are converted) for a dir or symlink entry whose realpath lies under bin/ or skills/ of an old CCA tree (lib/cca-env.sh + bin/cca-run-on-server); linked ancestors, dangling links, old bin/ directly on PATH and empty PATH entries (CWD) covered; nothing inside an old tree is opened or listed (tests guard os.scandir, open and io.open). [legacy] table removed from doc-1, doc-2, config and fixtures; TASK-1.5, 1.6, 1.10, 2 updated. Code and security reviews closed with no findings.
<!-- SECTION:FINAL_SUMMARY:END -->
