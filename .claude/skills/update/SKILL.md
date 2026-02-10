---
name: update
description: Pull framework updates from the upstream Clyde repo into this project
user_invocable: true
---

# Update

Pull the latest Clyde framework files into this project without affecting project code, inputs, or outputs.

## Steps

### 1. Run Diff

```bash
python3 scripts/update-framework.py diff
```

**If exit code 1** and the error mentions no `clyde` remote:
- Ask the user for the Clyde framework repo URL using AskUserQuestion:
  - **Use default** — `https://github.com/BradGraber/clyde.git`
  - **Custom URL** — the user provides their own
- Run `git remote add clyde <url>`, then re-run the diff command.

**If exit code 2** — already up to date. Tell the user, done.

**If exit code 0** — show the script output to the user and proceed to step 2.

### 2. Confirm

Ask the user to confirm using AskUserQuestion:
- **Apply updates** — sync all framework files now
- **Cancel** — abort without changes

### 3. Apply

```bash
python3 scripts/update-framework.py apply
```

Show the script output (summary, review instructions, any warnings about schema migration or restart).

## Notes

- This skill never touches `project-workspace/`, `input/`, or `output/`
- The `clyde` remote is set up by `/init` (renamed from `origin`)
- For existing projects that ran an older `/init`, step 1 handles adding the remote retroactively
