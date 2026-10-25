# cca clean

Deletes old entries of the project's `tmp/` (the one next to `.cca.toml`), so work files
do not pile up while unfinished work stays.

```
cca clean [--days N] [--apply]
```

- Without `--apply` it only plans: `DELETE <entry> <age>d <size>` or `KEEP <entry> <age>d`,
  a summary `--- delete=N (S MB) keep=M ---` and
  `PLAN - nothing deleted (add --apply to delete)`.
- Each top-level entry of `tmp/` is one unit. A file or link is old when its own mtime is
  older than N days (default 30, `[clean] days`). A directory is old only when its
  **newest** file or subdirectory is; then it is deleted whole. A directory with one
  recent file is kept whole, so keep unfinished work in a subdirectory you touch.
- Always kept (`KEEP <entry> (protected)`): the names in `[clean] keep` and the directory
  of `cloudflare.export_dir` (the DNS/WAF rollback snapshots, default `tmp/cloudflare`).
- Links are never followed: a link is deleted as a link. A directory that is, or
  contains, another filesystem (mount point) is kept whole. An entry that cannot be read
  is kept (`cannot read`), exit 1.
- `tmp/` missing: nothing to do (exit 0); `tmp/` a link or not a directory: exit 2.

Exit 0 done; 1 an entry could not be read or deleted; 2 usage or config error.
