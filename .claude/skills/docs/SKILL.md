---
name: docs
description: Identify and obtain reference documentation for external APIs and services
user_invocable: true
---

# Reference Documentation

Identify missing reference documentation and obtain it. Covers external API docs (Schwab, Reddit, OpenAI, etc.) and focused tech stack extracts (SQLite JSON functions, Vue Composition API, etc.).

## Step 1: Detect Mode

Check if `.claude/rules/dev-mode.md` exists:
- **Exists (dev mode)**: Target directory = `docs/` (framework-shipped, synced to all projects via `/update`)
- **Does not exist (project mode)**: Target directory = `input/docs/` (project-specific, never touched by `/update`)

Ensure the target directory exists (create if needed with `mkdir -p`).

## Step 2: Inventory Existing Docs

List `.md` files in both `docs/` and `input/docs/` (either may not exist). Present to the user:

```
Reference Documentation Inventory:
  Framework docs (docs/): [list of filenames, or "none"]
  Project docs (input/docs/): [list of filenames, or "none"]
```

## Step 3: Identify Gaps

Scan available project sources to identify what reference documentation might be needed:

- **`input/PRD.md`** (if exists): Look for references to external APIs, services, SDKs, third-party integrations
- **`output/technical-brief.md`** (if exists): Look for tech stack choices — languages, frameworks, databases, libraries — where focused reference extracts might help implementers

Cross-reference these against existing docs in both directories. Report:

```
Found docs for: [matched items]
Potentially missing:
  - [API/service name] — referenced in [PRD section / tech brief]
  - [library/framework] — referenced in [PRD section / tech brief]
```

If neither PRD nor technical brief exists, ask the user what docs they need using AskUserQuestion.

Not every gap needs a doc — well-known libraries (Python stdlib, basic Flask usage, etc.) are covered by model training. Focus on:
- External APIs with specific endpoints, auth patterns, or response formats
- Less common libraries or version-specific features
- Project-specific configurations or patterns

### Variant Cross-Reference

When identifying library gaps, cross-reference the project's **framework/runtime** against the **library variants** available. Common mismatches to flag:

- **Async frameworks** (FastAPI, aiohttp, Quart) + sync libraries → prefer async variants (e.g., `asyncpraw` over `praw`, `aiohttp` over `requests`, `asyncpg` over `psycopg2`)
- **Type-annotated codebases** → prefer typed client libraries where available

If both sync and async variants exist for a library the project uses, include docs for the variant that matches the framework. Note the mismatch in the gap report so the user can confirm.

## Step 4: Obtain Missing Docs

For each identified gap, ask the user using AskUserQuestion:
- **Provide URL** — fetch from a web URL
- **Provide file path** — copy from a local file
- **Skip** — implementers will rely on training data for this one

### For URLs
Use WebFetch to retrieve the content. Clean it into structured markdown:
- Clear section headers for endpoints, parameters, response formats
- Markdown tables for parameters (name, type, required, description)
- Code blocks for JSON request/response examples
- Remove navigation, ads, and other non-content elements

Save to the target directory (from Step 1) with a descriptive kebab-case filename (e.g., `schwab-market-data-api.md`, `sqlite-json1-functions.md`).

### For file paths
Read the file and write a copy to the target directory.

## Step 5: Report

Present a final summary:

```
Reference Documentation Summary:
  Framework docs (docs/): [list]
  Project docs (input/docs/): [list]
  Skipped: [list of gaps the user chose to skip, or "none"]

Target directory for this session: [docs/ or input/docs/]
```

If docs were added and `/analyze` has already been run (output/plan.db exists), remind the user that implementers will automatically see the new docs listed in their available reference documentation during the next implementation run.
