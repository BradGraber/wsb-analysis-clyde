---
name: validate
description: Validate a completed or in-progress implementation phase — run 7 health checks against logs and plan.db
user_invocable: true
---

# Validate

Run `scripts/validate-phase.py` to check phase health.

## Usage

- `/validate phase-b` — validate a specific phase
- `/validate` — auto-detect the most relevant phase

## Steps

1. Parse the user's argument (if any) as the phase ID.
2. Run the validation script:
   - With phase ID: `python3 scripts/validate-phase.py PHASE_ID`
   - Without: `python3 scripts/validate-phase.py --auto`
3. Present the report to the user.
4. If any checks show FAIL, briefly explain what the failure means and suggest next steps.
5. If all checks show NOT_EXERCISED, remind the user to enable logging first (`/logs on`) and that events accumulate during implementation.
