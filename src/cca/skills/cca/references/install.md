# cca install skills

`cca install skills [NAME] [--target DIR]` symlinks the skills shipped with the installed
cca into `DIR` (default `.claude/skills` in the current directory; it must exist). NAME
limits it to one skill.

- Idempotent: links that already point to the installed skill are left as they are.
- It replaces only links it owns: links it recorded in `DIR/.cca-skills.json`, or links
  into another cca install's skills. Any other file, directory or link with the same
  name is left untouched and reported (exit 1).
- After `uv tool install --reinstall` the links stay valid (same install path).
- Needs symlink support; without it the command fails with an error.
