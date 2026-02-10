#!/usr/bin/env python3
"""
update-framework.py — Programmatic framework update from upstream Clyde remote.

Zero external dependencies (Python 3 stdlib only).
Fetches from the 'clyde' remote, compares manifest-listed files,
and optionally applies changes.

Usage:
  python3 scripts/update-framework.py diff     # Show what would change
  python3 scripts/update-framework.py apply    # Apply the changes

Exit codes:
  0 — success (changes found/applied)
  1 — error (no remote, fetch failed, etc.)
  2 — no changes (already up to date)
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REMOTE = "clyde"
BRANCH = "main"
REF = f"{REMOTE}/{BRANCH}"
MANIFEST_PATH = ".claude/framework-manifest"

# Files loaded at Claude Code session startup — changes require restart
STARTUP_FILES = {
    ".claude/settings.json",
    "CLAUDE.md",
}
STARTUP_PREFIXES = [
    ".claude/rules/",
]

EXCLUDE_DIRS = {"__pycache__"}


# ---------------------------------------------------------------------------
# Git helpers
# ---------------------------------------------------------------------------

def git(*args, capture=True, check=True):
    """Run a git command and return stdout."""
    result = subprocess.run(
        ["git"] + list(args),
        capture_output=capture,
        text=True,
        check=False,
    )
    if check and result.returncode != 0:
        return None, result.stderr.strip()
    return result.stdout.strip(), None


def git_fetch():
    """Fetch from the clyde remote."""
    # Check remote exists
    out, err = git("remote", "get-url", REMOTE)
    if out is None:
        print(f"ERROR: No '{REMOTE}' remote found.", file=sys.stderr)
        print("Run /update from Claude Code to set it up, or add it manually:", file=sys.stderr)
        print(f"  git remote add {REMOTE} <url>", file=sys.stderr)
        sys.exit(1)

    print(f"Fetching from {REMOTE} ({out})...")
    _, err = git("fetch", REMOTE)
    if err and "error" in err.lower():
        print(f"ERROR: fetch failed: {err}", file=sys.stderr)
        sys.exit(1)


def git_file_exists_remote(path):
    """Check if a file exists in the remote ref."""
    out, _ = git("cat-file", "-t", f"{REF}:{path}", check=False)
    return out is not None and "blob" in out


def git_ls_tree(dir_path):
    """List files in a directory at the remote ref."""
    out, _ = git("ls-tree", "--name-only", REF, f"{dir_path}/", check=False)
    if out is None:
        return []
    return [line for line in out.splitlines() if line]


def git_diff_file(path):
    """Check if a file differs between HEAD and the remote ref."""
    out, _ = git("diff", "--quiet", "HEAD", REF, "--", path, check=False)
    # --quiet exits 0 if no diff, 1 if diff exists
    # We need to check the return code directly
    result = subprocess.run(
        ["git", "diff", "--quiet", "HEAD", REF, "--", path],
        capture_output=True,
    )
    return result.returncode != 0  # True = file has changes


def git_checkout_file(path):
    """Checkout a file from the remote ref."""
    subprocess.run(
        ["git", "checkout", REF, "--", path],
        check=True,
        capture_output=True,
    )


def local_file_exists(path):
    """Check if a file exists in the working tree."""
    return Path(path).exists()


def local_dir_files(dir_path):
    """List files in a local directory, excluding EXCLUDE_DIRS."""
    result = []
    d = Path(dir_path)
    if not d.is_dir():
        return result
    for f in d.iterdir():
        if f.name in EXCLUDE_DIRS:
            continue
        if f.is_file():
            result.append(f.name)
    return sorted(result)


# ---------------------------------------------------------------------------
# Manifest parsing
# ---------------------------------------------------------------------------

def parse_manifest(text):
    """Parse the framework manifest into directory and file entries."""
    dirs = []
    files = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("D "):
            dirs.append(line[2:].strip())
        elif line.startswith("F "):
            files.append(line[2:].strip())
    return dirs, files


def read_remote_manifest():
    """Read and parse the manifest from the remote ref."""
    out, err = git("show", f"{REF}:{MANIFEST_PATH}")
    if out is None:
        print(f"ERROR: Could not read manifest from {REF}:{MANIFEST_PATH}", file=sys.stderr)
        if err:
            print(f"  {err}", file=sys.stderr)
        sys.exit(1)
    return parse_manifest(out)


# ---------------------------------------------------------------------------
# Comparison logic
# ---------------------------------------------------------------------------

# Status constants
NEW = "NEW"
CHANGED = "CHANGED"
UNCHANGED = "UNCHANGED"
DELETE = "DELETE"
ORPHAN = "ORPHAN"

STATUS_TAG = {
    NEW: "[NEW]",
    CHANGED: "[CHANGED]",
    UNCHANGED: "[UNCHANGED]",
    DELETE: "[DELETE]",
    ORPHAN: "[ORPHAN]",
}


def compare_directory(dir_path):
    """Compare a directory entry. Returns list of (filename, status)."""
    results = []
    remote_files = [os.path.basename(f) for f in git_ls_tree(dir_path)]
    local_files = local_dir_files(dir_path)

    all_files = sorted(set(remote_files) | set(local_files))

    for fname in all_files:
        fpath = f"{dir_path}/{fname}"
        in_remote = fname in remote_files
        in_local = fname in local_files

        if in_remote and not in_local:
            results.append((fname, NEW))
        elif in_remote and in_local:
            if git_diff_file(fpath):
                results.append((fname, CHANGED))
            else:
                results.append((fname, UNCHANGED))
        elif in_local and not in_remote:
            results.append((fname, DELETE))

    return results


def compare_file(file_path):
    """Compare a single file entry. Returns status."""
    in_remote = git_file_exists_remote(file_path)
    in_local = local_file_exists(file_path)

    if in_remote and not in_local:
        return NEW
    elif in_remote and in_local:
        return CHANGED if git_diff_file(file_path) else UNCHANGED
    elif in_local and not in_remote:
        return ORPHAN
    else:
        return None  # not in either — skip


# ---------------------------------------------------------------------------
# Diff report
# ---------------------------------------------------------------------------

def build_report(manifest_dirs, manifest_files):
    """Build the full comparison report. Returns (report_lines, counts, changed_paths)."""
    lines = []
    counts = {NEW: 0, CHANGED: 0, UNCHANGED: 0, DELETE: 0, ORPHAN: 0}
    changed_paths = []  # paths that are NEW, CHANGED, or DELETE

    # Directory entries
    for dir_path in manifest_dirs:
        results = compare_directory(dir_path)
        if not results:
            continue
        lines.append(f"{dir_path}/")
        for fname, status in results:
            tag = STATUS_TAG[status]
            lines.append(f"  {tag:14s} {fname}")
            counts[status] += 1
            if status in (NEW, CHANGED, DELETE):
                changed_paths.append(f"{dir_path}/{fname}")
        lines.append("")

    # File entries
    file_results = []
    for file_path in manifest_files:
        status = compare_file(file_path)
        if status is None:
            continue
        file_results.append((file_path, status))
        counts[status] += 1
        if status in (NEW, CHANGED, ORPHAN):
            changed_paths.append(file_path)

    if file_results:
        max_len = max(len(fp) for fp, _ in file_results)
        for file_path, status in file_results:
            tag = STATUS_TAG[status]
            lines.append(f"{file_path:{max_len}s}   {tag}")
        lines.append("")

    return lines, counts, changed_paths


def print_report(lines, counts):
    """Print the diff report and summary."""
    print()
    for line in lines:
        print(line)

    parts = []
    if counts[NEW]:
        parts.append(f"{counts[NEW]} new")
    if counts[CHANGED]:
        parts.append(f"{counts[CHANGED]} changed")
    if counts[DELETE]:
        parts.append(f"{counts[DELETE]} deleted")
    if counts[ORPHAN]:
        parts.append(f"{counts[ORPHAN]} orphaned")
    parts.append(f"{counts[UNCHANGED]} unchanged")

    print(f"Summary: {', '.join(parts)}")


# ---------------------------------------------------------------------------
# Schema migration check
# ---------------------------------------------------------------------------

def check_schema_migration(changed_paths):
    """If schema.sql changed and plan.db exists, print migration warning."""
    if "schema.sql" not in changed_paths:
        return

    plan_db = Path("output/plan.db")
    if not plan_db.exists():
        return

    print()
    print("⚠  schema.sql has changed and output/plan.db exists.")

    # Check task progress
    import sqlite3
    conn = sqlite3.connect(str(plan_db))
    rows = conn.execute("SELECT status, COUNT(*) as cnt FROM tasks GROUP BY status").fetchall()
    conn.close()

    status_counts = {row[0]: row[1] for row in rows}
    has_progress = any(
        status_counts.get(s, 0) > 0
        for s in ("in_progress", "complete", "skipped")
    )

    if has_progress:
        print("   Implementation work is in progress. plan.db may need manual migration.")
        print("   Review the schema diff and apply changes carefully to preserve progress.")
    else:
        print("   No implementation work has started. You can safely re-run /analyze")
        print("   after this update to rebuild plan.db with the new schema.")


# ---------------------------------------------------------------------------
# Restart check
# ---------------------------------------------------------------------------

def needs_restart(changed_paths):
    """Check if any changed files require a Claude Code restart."""
    for path in changed_paths:
        if path in STARTUP_FILES:
            return True
        for prefix in STARTUP_PREFIXES:
            if path.startswith(prefix):
                return True
    return False


# ---------------------------------------------------------------------------
# Apply changes
# ---------------------------------------------------------------------------

def apply_changes(manifest_dirs, manifest_files, changed_paths):
    """Apply framework updates from the remote ref."""
    applied = {NEW: 0, CHANGED: 0, DELETE: 0}

    # Directory entries
    for dir_path in manifest_dirs:
        results = compare_directory(dir_path)
        for fname, status in results:
            fpath = f"{dir_path}/{fname}"
            if status == DELETE:
                Path(fpath).unlink()
                applied[DELETE] += 1
            elif status in (NEW, CHANGED):
                git_checkout_file(fpath)
                applied[status] += 1

    # File entries
    for file_path in manifest_files:
        status = compare_file(file_path)
        if status in (NEW, CHANGED):
            git_checkout_file(file_path)
            applied[status] += 1

    return applied


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_diff():
    """Show what would change."""
    git_fetch()

    manifest_dirs, manifest_files = read_remote_manifest()
    lines, counts, changed_paths = build_report(manifest_dirs, manifest_files)

    total_changes = counts[NEW] + counts[CHANGED] + counts[DELETE] + counts[ORPHAN]
    if total_changes == 0:
        print("\nAlready up to date.")
        sys.exit(2)

    print_report(lines, counts)
    check_schema_migration(changed_paths)

    if needs_restart(changed_paths):
        print()
        print("Note: Some updated files are loaded at session startup.")
        print("Restart Claude Code after applying for changes to take full effect.")


def cmd_apply():
    """Apply framework updates."""
    git_fetch()

    manifest_dirs, manifest_files = read_remote_manifest()
    lines, counts, changed_paths = build_report(manifest_dirs, manifest_files)

    total_changes = counts[NEW] + counts[CHANGED] + counts[DELETE] + counts[ORPHAN]
    if total_changes == 0:
        print("\nAlready up to date.")
        sys.exit(2)

    print_report(lines, counts)

    # Apply
    print("\nApplying updates...")
    applied = apply_changes(manifest_dirs, manifest_files, changed_paths)

    print()
    print("Framework updated from clyde/main.")
    print()
    if applied[NEW]:
        print(f"  Added:   {applied[NEW]} files")
    if applied[CHANGED]:
        print(f"  Updated: {applied[CHANGED]} files")
    if applied[DELETE]:
        print(f"  Deleted: {applied[DELETE]} files")
    print()
    print("Changes are staged. Review with:")
    print("  git diff --cached")
    print()
    print("When satisfied, commit with:")
    print('  git commit -m "Update framework from upstream Clyde"')

    check_schema_migration(changed_paths)

    if needs_restart(changed_paths):
        print()
        print("Note: Some updated files are loaded at session startup.")
        print("Restart Claude Code after applying for changes to take full effect.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Update framework files from the upstream Clyde remote."
    )
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("diff", help="Show what would change")
    sub.add_parser("apply", help="Apply the changes")

    args = parser.parse_args()

    if args.command == "diff":
        cmd_diff()
    elif args.command == "apply":
        cmd_apply()
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
