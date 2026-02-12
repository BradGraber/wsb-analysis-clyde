# Python Virtual Environment (venv) Patterns

**Type:** Environment Setup | **Applies to:** Python projects with third-party dependencies

> Python projects typically isolate dependencies in a virtual environment (`venv`). When a venv exists, **all Python commands must activate it first** — bare `python`, `pip`, and `pytest` use the system Python, which lacks project dependencies.

## Detection

The `./clyde` wrapper detects venv automatically at launch and promotes this doc to the priority tier in `.claude/rules/project-env.md`. You do not need to probe for venv yourself. Common locations: `project-workspace/venv/`, `project-workspace/.venv/`.

## Activation

Activate the venv before running any Python command. Always use **subshell syntax** to prevent CWD drift:

```bash
# Correct — subshell isolates CWD and activation
(cd project-workspace && source venv/bin/activate && python -m pytest tests/ -v)

# Correct — .venv variant
(cd project-workspace && source .venv/bin/activate && pip install -r requirements.txt)
```

Do **not** use bare commands:

```bash
# WRONG — uses system Python, missing project dependencies
(cd project-workspace && python -m pytest tests/ -v)

# WRONG — pip installs to system Python, not project venv
(cd project-workspace && pip install some-package)

# WRONG — bare cd causes CWD drift for subsequent commands
cd project-workspace && source venv/bin/activate && pytest
```

## Common Commands

All commands assume venv at `project-workspace/venv/`. Adjust path if `.venv/` is used.

**Run tests:**
```bash
(cd project-workspace && source venv/bin/activate && python -m pytest tests/ -v)
```

**Install dependencies:**
```bash
(cd project-workspace && source venv/bin/activate && pip install -r requirements.txt)
```

**Run a Python script:**
```bash
(cd project-workspace && source venv/bin/activate && python src/some_script.py)
```

**Install a single package:**
```bash
(cd project-workspace && source venv/bin/activate && pip install some-package)
```

## Why This Matters

- `python` and `pip` resolve to the **system Python** by default, which does not have the project's installed packages
- Running `pip install` without activation installs packages globally (or fails due to permissions), not into the project's isolated environment
- Test runs fail with `ModuleNotFoundError` when the venv is not activated, because pytest cannot find the project's dependencies
