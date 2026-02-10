---
name: update
description: Pull framework updates from the upstream Clyde repo into this project
user_invocable: true
---

# Update

Pull the latest Clyde framework files into this project without affecting project code, inputs, or outputs.

## Steps

### 1. Check the `clyde` Remote

Run `git remote get-url clyde 2>/dev/null` to check if the `clyde` remote exists.

**If it exists:** Show the URL and proceed to step 2.

**If it doesn't exist:** This project was initialized before `/update` existed, or the remote was removed. Ask the user for the Clyde framework repo URL using AskUserQuestion:

- **Use default** — `https://github.com/BradGraber/clyde.git`
- **Custom URL** — the user provides their own (e.g., a local path like `~/clyde` for framework developers)

Then run:
```bash
git remote add clyde <url>
```

### 2. Fetch Upstream

```bash
git fetch clyde
```

If this fails (network error, invalid remote), report the error and stop.

### 3. Read the Remote Manifest

Read the upstream manifest to determine which files are framework-owned:

```bash
git show clyde/main:.claude/framework-manifest
```

**Important:** Always use the **remote** version of the manifest, not the local copy. This ensures newly added framework paths are included even if the local manifest is outdated.

Parse the manifest format:
- Lines starting with `#` are comments — skip them
- Blank lines — skip
- `D <dir>` — directory-replace entry (sync all files, delete stale ones)
- `F <file>` — individual file entry

### 4. Diff Report

For each manifest entry, compare the local version against `clyde/main`:

**For `D` (directory) entries:**
1. List files in the local directory (excluding `__pycache__/`)
2. List files in the upstream directory: `git ls-tree --name-only clyde/main <dir>/`
3. For each file:
   - In upstream but not local → `[NEW]`
   - In both → compare with `git diff HEAD clyde/main -- <dir>/<file>`. If different → `[CHANGED]`, if same → `[UNCHANGED]`
   - In local but not upstream → `[DELETE]` (stale file, will be removed)

**For `F` (file) entries:**
1. Check if the file exists locally and in upstream
2. If only in upstream → `[NEW]`
3. If in both → compare with `git diff HEAD clyde/main -- <file>`. If different → `[CHANGED]`, if same → `[UNCHANGED]`
4. If only local → `[ORPHAN]` (framework removed this file — flag for user attention)

**Display format:**
```
Comparing local framework files against clyde/main...

.claude/agents/
  [DELETE]    analyzer.md
  [NEW]       tech-brief-drafter.md
  [CHANGED]   implementer.md
  [UNCHANGED] phase-extractor.md

scripts/
  [CHANGED]   plan-ops.py
  [UNCHANGED] build-plan-db.py

.claude/rules/phase2-implement.md   [CHANGED]
schema.sql                           [CHANGED]
CLAUDE.md                            [CHANGED]
clyde                                [UNCHANGED]
```

### 5. Schema Migration Check

If `schema.sql` is `[CHANGED]` **and** `output/plan.db` exists:

1. Show the schema diff: `git diff HEAD clyde/main -- schema.sql`
2. Check project progress — run `sqlite3 output/plan.db "SELECT status, COUNT(*) FROM tasks GROUP BY status;"`
3. Based on progress:
   - **All tasks pending (no work started):** "Schema has changed. Since no implementation work has started, you can safely re-run `/analyze` after this update to rebuild plan.db with the new schema."
   - **Some tasks in_progress or complete:** "Schema has changed and implementation work is in progress. plan.db may need manual migration. Review the schema diff above and apply changes carefully to preserve your progress."

Do NOT auto-migrate. Just warn and advise.

### 6. Confirm and Apply

Show a summary:
```
Summary: N new, N changed, N deleted, N unchanged

Schema: [changed — see warning above / unchanged / no plan.db]
```

Ask the user to confirm before applying. Use AskUserQuestion:
- **Apply updates** — sync all framework files now
- **Cancel** — abort without changes

**If confirmed**, apply changes in this order:

1. **Directory entries (`D`):**
   - Delete stale local files (those marked `[DELETE]`)
   - For each file in the upstream directory, checkout from remote:
     ```bash
     git checkout clyde/main -- <dir>/<file>
     ```

2. **File entries (`F`):**
   ```bash
   git checkout clyde/main -- <file>
   ```

3. All changes land in the staging area (git index). The user can review with `git diff --cached` and commit when ready.

### 7. Summary

Show what was done:

```
Framework updated from clyde/main.

  Added:     N files
  Changed:   N files
  Deleted:   N files
  Unchanged: N files (skipped)

Changes are staged. Review with:
  git diff --cached

When satisfied, commit with:
  git commit -m "Update framework from upstream Clyde"
```

If schema changed, repeat the migration warning here.

## Notes

- This skill never touches `project-workspace/`, `input/`, or `output/`
- The `clyde` remote is set up by `/init` (renamed from `origin`)
- For existing projects that ran an older `/init`, step 1 handles adding the remote retroactively
- Framework developers can point `clyde` at a local repo path (e.g., `~/clyde`) for testing uncommitted changes — just commit locally first, then `git fetch clyde` will pick them up
