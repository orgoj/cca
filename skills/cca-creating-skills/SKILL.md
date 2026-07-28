---
name: cca-creating-skills
description: Create new CCA skills in shared repository with automatic linking
argument-hint: "\"skill-name\" \"description\""
allowed-tools: Bash(*), Read(*), Write(*), Edit(*), Glob(*)
---

# CCA Skill Creator

**Purpose:** Create new CCA skills in the shared repository and link them to the current project.

**Skills are referenced by NAME, never by path.** In skill/guide text always write just the skill
name (`cca-searching`, `cca-core`) — no directories, no absolute paths, no symlink targets.

## Steps

### 1. Analysis
**Decision: CCA skill (shared) vs project skill?**
- **Shared** — applies to server administration generally, usable across projects.
- **Project** — specific to one project (its servers/services): create directly in `.claude/skills/`.

**Arguments:**
- `skill-name` - Name without `cca-` prefix (e.g., "diagnostics", "health-check")
- `description` - One-line description for skill frontmatter

### 2. Execution
**Locate the shared skills directory** (never hardcode it — it differs per machine):
```bash
SHARED=$(dirname "$(readlink .claude/skills/cca-core)")
```

**Create the skill** in `$SHARED/cca-{name}/SKILL.md` (template below), then link it into the
project:
```bash
ln -s "$SHARED/cca-{name}" .claude/skills/cca-{name}
```

### 3. Verification
**Verify the link works:** `Read .claude/skills/cca-{name}/SKILL.md`.
**Test the skill:** invoke it by name.

## Critical Understanding

**CCA skills are SHARED between projects!**
- Changes to a shared skill affect ALL projects using it.
- Keep shared skills project-agnostic AND machine-agnostic: no project servers/domains,
  no absolute paths, no per-machine values. Project specifics belong in that project's
  guides (see `cca-saving-guides`).

## Skill Structure

```markdown
---
name: cca-{name}
description: Brief one-line description
allowed-tools: ...
---

# Skill Title

## Steps
### 1. Analysis
### 2. Execution
### 3. Verification
```


<!-- SHARED SKILL: Keep project-agnostic. For project-specific extensions, create a local skill. -->
