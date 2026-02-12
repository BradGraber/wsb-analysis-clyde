#!/usr/bin/env python3
"""
validate-phase.py — Post-phase validation for the Clyde framework.

Reads log files + plan.db and runs two sets of checks:
  1. Health checks (8) — generic phase health (lifecycle, tests, errors, gates, compaction, etc.)
  2. Fix validations (cumulative) — explicit checks for known framework fixes,
     grouped by the phase that first exercises them. All fix validations always
     run regardless of which phase is being validated (regression).

Standalone, stdlib-only. No external dependencies.

Usage:
  python3 scripts/validate-phase.py PHASE_ID [--json] [--project-root PATH]
  python3 scripts/validate-phase.py --auto [--json] [--project-root PATH]
"""

import argparse
import json
import sqlite3
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_jsonl(path):
    """Load a .jsonl file into a list of dicts. Returns [] if missing/empty."""
    if not path.exists():
        return []
    entries = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return entries


def _get_phase_item_ids(conn, phase_id):
    """Return sets of (story_ids, epic_ids) mapped to a phase."""
    rows = conn.execute(
        'SELECT item_type, item_id FROM phase_items WHERE phase_id = ?',
        (phase_id,)
    ).fetchall()
    story_ids = set()
    epic_ids = set()
    for r in rows:
        if r['item_type'] == 'story':
            story_ids.add(r['item_id'])
        elif r['item_type'] == 'epic':
            epic_ids.add(r['item_id'])
    # Also include stories belonging to mapped epics
    if epic_ids:
        placeholders = ','.join('?' for _ in epic_ids)
        extra = conn.execute(
            f'SELECT id FROM stories WHERE epic_id IN ({placeholders})',
            list(epic_ids)
        ).fetchall()
        for s in extra:
            story_ids.add(s['id'])
    return story_ids, epic_ids


def _get_phase_task_ids(conn, phase_id):
    """Return set of task IDs in a phase."""
    rows = conn.execute(
        'SELECT DISTINCT t.id FROM tasks t '
        'JOIN phase_items pi ON '
        '  (pi.item_type = \'story\' AND pi.item_id = t.story_id) '
        '  OR (pi.item_type = \'epic\' AND pi.item_id = t.epic_id) '
        'WHERE pi.phase_id = ?',
        (phase_id,)
    ).fetchall()
    return {r['id'] for r in rows}


def _filter_events(events, phase_task_ids, phase_story_ids, phase_id):
    """Filter events to those relevant to a phase."""
    filtered = []
    for e in events:
        ev = e.get('event', '')
        # Phase-level events
        if ev == 'phase_updated' and e.get('phase_id') == phase_id:
            filtered.append(e)
        # Task-level events
        elif ev in ('task_started', 'task_completed', 'task_skipped', 'task_retried'):
            if e.get('task_id') in phase_task_ids:
                filtered.append(e)
        # Story gate events
        elif ev == 'story_gate_updated':
            if e.get('story_id') in phase_story_ids:
                filtered.append(e)
        # Batch checks (not phase-scoped — include all)
        elif ev == 'batch_check':
            filtered.append(e)
    return filtered


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------

PASS = 'PASS'
FAIL = 'FAIL'
NOT_EXERCISED = 'NOT_EXERCISED'


def check_lifecycle(events, phase_task_ids):
    """Check lifecycle integrity: phase transitions in order, no orphaned starts."""
    details = {}

    # Phase transitions
    phase_events = [e for e in events if e.get('event') == 'phase_updated']
    statuses = [e.get('status') for e in phase_events]
    valid_order = ['tests_written', 'in_progress', 'gate_pending', 'complete']
    order_ok = True
    if statuses:
        # Each status should appear at or after its position in valid_order
        last_idx = -1
        for s in statuses:
            if s in valid_order:
                idx = valid_order.index(s)
                if idx < last_idx:
                    order_ok = False
                    break
                last_idx = idx
    details['phase_transitions'] = statuses
    details['transitions_in_order'] = order_ok

    # Check for orphaned task starts (started but never completed/skipped)
    started = set()
    resolved = set()
    for e in events:
        ev = e.get('event', '')
        tid = e.get('task_id')
        if ev == 'task_started' and tid:
            started.add(tid)
        elif ev in ('task_completed', 'task_skipped') and tid:
            resolved.add(tid)
    orphans = started - resolved
    details['tasks_started'] = len(started)
    details['tasks_resolved'] = len(resolved)
    details['orphaned_starts'] = sorted(orphans)

    if not phase_events and not started:
        return NOT_EXERCISED, 'No lifecycle events found', details

    verdict = PASS if (order_ok and not orphans) else FAIL
    issues = []
    if not order_ok:
        issues.append('Phase transitions out of order')
    if orphans:
        issues.append(f'{len(orphans)} task(s) started but never completed/skipped: {sorted(orphans)}')
    message = '; '.join(issues) if issues else 'All transitions valid, no orphaned tasks'
    return verdict, message, details


def check_test_writer(project_root):
    """Check that test-writer output exists with expected sections."""
    conventions = project_root / 'project-workspace' / 'tests' / 'conventions.md'
    details = {'path': str(conventions), 'exists': conventions.exists()}

    if not conventions.exists():
        return NOT_EXERCISED, 'conventions.md not found (test-writer may not have run)', details

    content = conventions.read_text()
    expected_sections = [
        ('Test Runner',),
        ('Module Path', 'Module Structure', 'Import Pattern'),
        ('Naming',),
    ]
    found = []
    missing = []
    for group in expected_sections:
        label = group[0]
        if any(variant.lower() in content.lower() for variant in group):
            found.append(label)
        else:
            missing.append(label)

    details['sections_found'] = found
    details['sections_missing'] = missing

    verdict = PASS if not missing else FAIL
    msg = f'Found sections: {found}' if not missing else f'Missing sections: {missing}'
    return verdict, msg, details


def check_permissions(hook_decisions):
    """Summarize permission hook decisions — FAIL if any fail-safe escapes detected."""
    if not hook_decisions:
        return NOT_EXERCISED, 'No hook decisions logged', {}

    total = len(hook_decisions)
    allow = sum(1 for d in hook_decisions if d.get('decision') == 'allow')
    ask = sum(1 for d in hook_decisions if d.get('decision') == 'ask')
    fail_safe = sum(1 for d in hook_decisions if d.get('decision') == 'fail_safe')

    # Break down ask reasons
    ask_reasons = {}
    for d in hook_decisions:
        if d.get('decision') == 'ask':
            reason = d.get('reason', 'unknown')
            ask_reasons[reason] = ask_reasons.get(reason, 0) + 1

    # Break down fail-safe reasons
    fail_safe_reasons = {}
    for d in hook_decisions:
        if d.get('decision') == 'fail_safe':
            reason = d.get('reason', 'unknown')
            fail_safe_reasons[reason] = fail_safe_reasons.get(reason, 0) + 1

    pct = round(allow / total * 100, 1) if total else 0
    details = {
        'total': total,
        'allow': allow,
        'ask': ask,
        'fail_safe': fail_safe,
        'auto_approve_rate': pct,
        'ask_reasons': ask_reasons,
        'fail_safe_reasons': fail_safe_reasons,
    }
    msg = f'{total} decisions: {allow} auto-approved ({pct}%), {ask} prompted'
    if fail_safe:
        msg += f', {fail_safe} fail-safe (commands escaped hook)'
        return FAIL, msg, details
    return PASS, msg, details


def _is_test_command(event):
    """Check if a PostToolUseFailure event is an expected test run failure."""
    inp = event.get('input', {})
    cmd = inp.get('command', '') if isinstance(inp, dict) else ''
    return 'pytest' in cmd


def check_error_free(orchestrator_events):
    """Check orchestrator log for framework errors (filtering expected test failures)."""
    if not orchestrator_events:
        return NOT_EXERCISED, 'No orchestrator events logged', {}

    errors = []
    test_failures = 0
    for e in orchestrator_events:
        if e.get('event') == 'PostToolUseFailure':
            if _is_test_command(e):
                test_failures += 1
            else:
                errors.append({
                    'tool': e.get('tool', ''),
                    'ts': e.get('ts', ''),
                })
        # Check Bash responses for plan-ops errors
        if e.get('tool') == 'Bash':
            resp = e.get('response', {})
            stdout = resp.get('stdout', '') if isinstance(resp, dict) else str(resp)
            if 'ERROR:' in stdout or 'Traceback' in stdout:
                inp = e.get('input', {})
                cmd = inp.get('command', '') if isinstance(inp, dict) else ''
                if 'plan-ops' in cmd:
                    errors.append({
                        'tool': 'Bash (plan-ops)',
                        'command': cmd[:200],
                        'ts': e.get('ts', ''),
                    })

    details = {
        'total_events': len(orchestrator_events),
        'errors': errors,
        'test_failures_filtered': test_failures,
    }
    filtered_note = f' ({test_failures} test failures filtered)' if test_failures else ''
    if errors:
        return FAIL, f'{len(errors)} framework error(s) found{filtered_note}', details
    return PASS, f'{len(orchestrator_events)} events checked, no framework errors{filtered_note}', details


def check_story_gates(conn, phase_id, phase_story_ids):
    """Check that all completed stories have non-pending gate_status."""
    completed = conn.execute(
        'SELECT id, title, gate_status FROM stories '
        'WHERE status = \'complete\' AND id IN ({})'.format(
            ','.join('?' for _ in phase_story_ids)
        ),
        list(phase_story_ids)
    ).fetchall() if phase_story_ids else []

    if not completed:
        return NOT_EXERCISED, 'No completed stories in this phase', {}

    pending_gates = [dict(s) for s in completed if s['gate_status'] in (None, 'pending')]
    passed_gates = [s['id'] for s in completed if s['gate_status'] == 'passed']
    failed_gates = [s['id'] for s in completed if s['gate_status'] == 'failed']

    details = {
        'completed_stories': len(completed),
        'passed': passed_gates,
        'failed': failed_gates,
        'pending': [s['id'] for s in pending_gates],
    }

    if pending_gates:
        return FAIL, f'{len(pending_gates)} completed story/stories with pending gate', details
    msg = f'{len(completed)} stories gated: {len(passed_gates)} passed, {len(failed_gates)} failed'
    return PASS, msg, details


def check_batch_counter(events):
    """Check that batch_check events increment sequentially."""
    batch_events = [e for e in events if e.get('event') == 'batch_check']
    if not batch_events:
        return NOT_EXERCISED, 'No batch_check events logged', {}

    # Find resets and check sequences between them
    sequences = []
    current_seq = []
    for e in batch_events:
        if e.get('reset'):
            if current_seq:
                sequences.append(current_seq)
            current_seq = []
        else:
            current_seq.append(e.get('batch', 0))
    if current_seq:
        sequences.append(current_seq)

    sequential = True
    for seq in sequences:
        for i in range(1, len(seq)):
            if seq[i] != seq[i - 1] + 1:
                sequential = False
                break

    details = {
        'total_checks': len(batch_events),
        'sequences': sequences,
        'sequential': sequential,
    }

    if not sequential:
        return FAIL, 'Batch counter has non-sequential increments', details
    max_batch = max(b for seq in sequences for b in seq) if any(sequences) else 0
    return PASS, f'{len(batch_events)} batch checks, max batch: {max_batch}', details


def check_process_cleanup(project_root, orchestrator_events):
    """Check that .spawned-pids is empty/missing and cleanup events exist."""
    pids_file = project_root / 'output' / '.spawned-pids'
    cleanup_log = project_root / 'output' / 'logs' / 'cleanup.log'

    pids_exist = pids_file.exists()
    pids_content = []
    if pids_exist:
        content = pids_file.read_text().strip()
        pids_content = [p for p in content.splitlines() if p.strip()]

    cleanup_logged = cleanup_log.exists() and cleanup_log.stat().st_size > 0

    details = {
        'pids_file_exists': pids_exist,
        'remaining_pids': pids_content,
        'cleanup_log_exists': cleanup_logged,
    }

    if not pids_exist and not cleanup_logged:
        return NOT_EXERCISED, 'No PID tracking or cleanup logs found', details

    if pids_content:
        return FAIL, f'{len(pids_content)} PIDs still in .spawned-pids', details

    msg = 'PID file clean'
    if cleanup_logged:
        msg += ', cleanup events logged'
    return PASS, msg, details


def check_compaction_health(events, orchestrator):
    """Check compaction frequency, state cleanliness, and post-compaction recovery."""
    compact_events = [e for e in events if e.get('event') == 'compaction']
    if not compact_events:
        return NOT_EXERCISED, 'No compaction events logged', {}

    batch_values = [e.get('batch', 0) for e in compact_events]
    mid_batch = sum(1 for e in compact_events if e.get('orphaned_tasks', 0) > 0)
    mid_gate = sum(1 for e in compact_events if e.get('pending_gates', 0) > 0)
    resume_actions = [e.get('resume_action', '') for e in compact_events]

    # Average batches per compaction cycle
    avg_per_cycle = sum(batch_values) / len(batch_values) if batch_values else 0

    # Post-compaction recovery analysis
    recovery = []
    for ce in compact_events:
        ce_ts = ce.get('ts', '')
        # Find next 10 orchestrator events after this compaction
        post_events = [o for o in orchestrator if o.get('ts', '') > ce_ts][:10]

        conventions_read = False
        plan_ops_called = False
        first_5_tools = []

        for o in post_events:
            tool = o.get('tool', '')
            if len(first_5_tools) < 5:
                first_5_tools.append(tool)

            # Check for conventions.md read
            if tool == 'Read':
                inp = o.get('input', {})
                path = inp.get('file_path', '') if isinstance(inp, dict) else ''
                if 'conventions.md' in path:
                    conventions_read = True

            # Check for plan-ops.py call
            if tool == 'Bash':
                inp = o.get('input', {})
                cmd = inp.get('command', '') if isinstance(inp, dict) else ''
                if 'plan-ops' in cmd:
                    plan_ops_called = True

        recovery.append({
            'compaction_ts': ce_ts,
            'batch_at_compaction': ce.get('batch', 0),
            'conventions_read': conventions_read,
            'plan_ops_called': plan_ops_called,
            'first_5_tools': first_5_tools,
        })

    details = {
        'total_compactions': len(compact_events),
        'batch_values': batch_values,
        'avg_batches_per_cycle': round(avg_per_cycle, 1),
        'mid_batch_compactions': mid_batch,
        'mid_gate_compactions': mid_gate,
        'resume_actions': resume_actions,
        'recovery_analysis': recovery,
    }

    # Check if any recovery lacked plan-ops calls.  This is WARN not FAIL because
    # end-of-session compactions (batch 8, budget stop) legitimately proceed to
    # /end-session rather than continuing the implementation loop.
    recovery_failures = [r for r in recovery if not r['plan_ops_called']]

    if recovery_failures:
        # FAIL only if ALL compactions lack recovery signals (likely a hook bug).
        # Mixed results (some recovered, some didn't) are WARN — the misses are
        # likely end-of-session compactions.
        if len(recovery_failures) == len(recovery):
            return FAIL, (
                f'{len(compact_events)} compaction(s), '
                f'none had post-compaction plan-ops calls'
            ), details
        return PASS, (
            f'{len(compact_events)} compaction(s), avg {avg_per_cycle:.1f} batches/cycle, '
            f'{len(recovery_failures)} without plan-ops call (likely end-of-session)'
        ), details

    if mid_batch > 0 or mid_gate > 0:
        return PASS, (
            f'{len(compact_events)} compaction(s), avg {avg_per_cycle:.1f} batches/cycle, '
            f'{mid_batch} mid-batch, {mid_gate} mid-gate (recovered)'
        ), details

    return PASS, (
        f'{len(compact_events)} compaction(s), avg {avg_per_cycle:.1f} batches/cycle, all clean'
    ), details


# ---------------------------------------------------------------------------
# Fix validations — explicit checks for known framework fixes
# ---------------------------------------------------------------------------
# Each fix_* function receives a ctx dict with:
#   hook_decisions, orchestrator, events, phase_events, project_root,
#   conn, phase_id, phase_status


def _get_bash_commands(orchestrator):
    """Extract (command, response_text) pairs from orchestrator Bash events."""
    results = []
    for e in orchestrator:
        if e.get('tool') != 'Bash':
            continue
        inp = e.get('input', {})
        cmd = inp.get('command', '') if isinstance(inp, dict) else ''
        resp = e.get('response', {})
        stdout = resp.get('stdout', '') if isinstance(resp, dict) else str(resp)
        results.append((cmd, stdout))
    return results


def fix_permission_spam(ctx):
    """Verify PreToolUse hook auto-approves chained (&&) commands."""
    decisions = ctx['hook_decisions']
    if not decisions:
        return NOT_EXERCISED, 'No hook decisions logged', {}

    # Find decisions for chained commands
    chained = [d for d in decisions if '&&' in d.get('command', '')]
    chained_allowed = [d for d in chained if d.get('decision') == 'allow']
    chained_asked = [d for d in chained if d.get('decision') == 'ask']

    # Check for false prompts on safe commands (asked but shouldn't have been)
    safe_keywords = ['plan-ops', 'pytest', 'python3', 'cat ', 'ls ', 'echo ']
    false_prompts = []
    for d in decisions:
        if d.get('decision') != 'ask':
            continue
        cmd = d.get('command', '')
        if any(kw in cmd for kw in safe_keywords):
            false_prompts.append(cmd[:100])

    details = {
        'total_decisions': len(decisions),
        'chained_total': len(chained),
        'chained_allowed': len(chained_allowed),
        'chained_asked': len(chained_asked),
        'false_prompts': false_prompts,
    }

    if not chained:
        return NOT_EXERCISED, 'No chained (&&) commands found in hook decisions', details

    issues = []
    if chained_asked:
        issues.append(f'{len(chained_asked)} chained command(s) prompted instead of auto-approved')
    if false_prompts:
        issues.append(f'{len(false_prompts)} false prompt(s) on safe commands')

    if issues:
        return FAIL, '; '.join(issues), details
    return PASS, f'{len(chained_allowed)} chained commands auto-approved, 0 false prompts', details


def fix_test_writer_alignment(ctx):
    """Verify phase-tasks was called to give test-writer task-level context."""
    bash_cmds = _get_bash_commands(ctx['orchestrator'])
    phase_tasks_calls = [cmd for cmd, _ in bash_cmds if 'phase-tasks' in cmd]

    details = {'phase_tasks_calls': len(phase_tasks_calls)}

    if not bash_cmds:
        return NOT_EXERCISED, 'No orchestrator events logged', details

    if not phase_tasks_calls:
        return NOT_EXERCISED, 'No phase-tasks calls found (test-writer may not have run yet)', details

    return PASS, f'phase-tasks called {len(phase_tasks_calls)} time(s) before test-writer', details


def fix_cwd_stability(ctx):
    """Verify story-files/phase-files calls succeed without CWD-related errors."""
    bash_cmds = _get_bash_commands(ctx['orchestrator'])
    relevant = [(cmd, resp) for cmd, resp in bash_cmds
                if 'story-files' in cmd or 'phase-files' in cmd]

    details = {'calls_found': len(relevant)}

    if not bash_cmds:
        return NOT_EXERCISED, 'No orchestrator events logged', details

    if not relevant:
        return NOT_EXERCISED, 'No story-files/phase-files calls found', details

    errors = []
    for cmd, resp in relevant:
        if 'ERROR' in resp or 'Traceback' in resp or 'No such file' in resp:
            errors.append(cmd[:150])

    details['errors'] = errors
    details['successful'] = len(relevant) - len(errors)

    if errors:
        return FAIL, f'{len(errors)} story-files/phase-files call(s) failed', details
    return PASS, f'{len(relevant)} story-files/phase-files call(s) succeeded', details


def fix_context_exhaustion(ctx):
    """Verify batch budget system functioned (batch events exist, phase progressed)."""
    batch_events = [e for e in ctx['events'] if e.get('event') == 'batch_check']
    phase_status = ctx['phase_status']

    details = {
        'batch_events': len(batch_events),
        'phase_status': phase_status,
    }

    if not batch_events:
        return NOT_EXERCISED, 'No batch_check events logged', details

    # Check that at least one non-reset batch was recorded
    increments = [e for e in batch_events if not e.get('reset')]
    resets = [e for e in batch_events if e.get('reset')]
    details['increments'] = len(increments)
    details['resets'] = len(resets)

    if not increments:
        return NOT_EXERCISED, 'Only reset events found, no batch increments', details

    # Phase should have progressed past tests_written
    progressed = phase_status in ('in_progress', 'gate_pending', 'complete')
    details['phase_progressed'] = progressed

    if not progressed:
        return FAIL, f'Batch events exist but phase stuck at {phase_status}', details

    max_batch = max(e.get('batch', 0) for e in increments)
    budget_stops = [e for e in increments if e.get('stop')]
    msg = f'{len(increments)} batches completed (max: {max_batch})'
    if budget_stops:
        msg += f', budget triggered {len(budget_stops)} stop(s)'
    return PASS, msg, details


def fix_orphan_processes(ctx):
    """Verify PID tracking and cleanup hooks functioned."""
    project_root = ctx['project_root']
    pids_file = project_root / 'output' / '.spawned-pids'
    cleanup_log = project_root / 'output' / 'logs' / 'cleanup.log'

    pids_exist = pids_file.exists()
    pids_content = []
    if pids_exist:
        content = pids_file.read_text().strip()
        pids_content = [p for p in content.splitlines() if p.strip()]

    cleanup_logged = cleanup_log.exists() and cleanup_log.stat().st_size > 0

    details = {
        'pids_file_exists': pids_exist,
        'remaining_pids': pids_content,
        'cleanup_log_exists': cleanup_logged,
    }

    if not pids_exist and not cleanup_logged:
        return NOT_EXERCISED, 'No PID tracking or cleanup logs found', details

    issues = []
    if pids_content:
        issues.append(f'{len(pids_content)} PIDs still in .spawned-pids after cleanup')

    if issues:
        return FAIL, '; '.join(issues), details

    msg = 'PID file clean'
    if cleanup_logged:
        msg += ', cleanup hook ran'
    return PASS, msg, details


def fix_reference_docs(ctx):
    """Verify list-docs was called and docs directories have content."""
    project_root = ctx['project_root']
    bash_cmds = _get_bash_commands(ctx['orchestrator'])
    list_docs_calls = [cmd for cmd, _ in bash_cmds if 'list-docs' in cmd]

    framework_docs = project_root / 'docs'
    project_docs = project_root / 'input' / 'docs'
    fw_files = list(framework_docs.glob('*.md')) if framework_docs.is_dir() else []
    proj_files = list(project_docs.glob('*.md')) if project_docs.is_dir() else []

    details = {
        'list_docs_calls': len(list_docs_calls),
        'framework_docs': len(fw_files),
        'project_docs': len(proj_files),
    }

    if not bash_cmds:
        return NOT_EXERCISED, 'No orchestrator events logged', details

    if not list_docs_calls:
        return NOT_EXERCISED, 'No list-docs calls found', details

    total_docs = len(fw_files) + len(proj_files)
    return PASS, f'list-docs called {len(list_docs_calls)} time(s), {total_docs} doc(s) available', details


def fix_tiered_docs(ctx):
    """Verify tiered doc system: project-env.md passed to subagents, venv usage taught."""
    project_root = ctx['project_root']
    orchestrator = ctx['orchestrator']

    # Early exit for dev mode (framework docs, not project docs)
    if (project_root / '.claude' / 'rules' / 'dev-mode.md').exists():
        return NOT_EXERCISED, 'Dev mode active (no project-env.md generation)', {'dev_mode': True}

    if not orchestrator:
        return NOT_EXERCISED, 'No orchestrator events logged', {}

    # --- Sub-check 1: Subagents received doc context ---
    task_spawns = [e for e in orchestrator
                   if e.get('tool') == 'Task' and e.get('event') == 'PostToolUse']
    spawns_with_docs = 0
    has_priority = False
    has_available = False
    for e in task_spawns:
        prompt = e.get('input', {}).get('prompt', '') if isinstance(e.get('input'), dict) else ''
        found_priority = 'Priority — read before running' in prompt
        found_available = 'Available on demand' in prompt
        if found_priority or found_available:
            spawns_with_docs += 1
        if found_priority:
            has_priority = True
        if found_available:
            has_available = True

    # --- Sub-check 2: No bare python/pip PostToolUseFailure (when venv exists) ---
    venv_dir = None
    if (project_root / 'project-workspace' / 'venv').is_dir():
        venv_dir = 'venv'
    elif (project_root / 'project-workspace' / '.venv').is_dir():
        venv_dir = '.venv'

    bare_failures = []
    if venv_dir:
        venv_patterns = ('venv/bin/', '.venv/bin/', 'activate')
        framework_patterns = ('plan-ops', 'validate-phase', 'plan.db')
        bare_keywords = ('python ', 'python3 ', 'pip ', 'pip3 ', 'pytest ')
        for e in orchestrator:
            if e.get('event') != 'PostToolUseFailure' or e.get('tool') != 'Bash':
                continue
            if _is_test_command(e):
                continue
            inp = e.get('input', {})
            cmd = inp.get('command', '') if isinstance(inp, dict) else ''
            if any(fp in cmd for fp in framework_patterns):
                continue
            if any(kw in cmd for kw in bare_keywords) and not any(vp in cmd for vp in venv_patterns):
                bare_failures.append({'command': cmd[:150], 'ts': e.get('ts', '')})

    # --- Sub-check 3: Docs directories have content ---
    fw_dir = project_root / 'docs'
    proj_dir = project_root / 'input' / 'docs'
    fw_files = list(fw_dir.glob('*.md')) if fw_dir.is_dir() else []
    proj_files = list(proj_dir.glob('*.md')) if proj_dir.is_dir() else []
    total_docs = len(fw_files) + len(proj_files)

    details = {
        'total_task_spawns': len(task_spawns),
        'spawns_with_docs': spawns_with_docs,
        'priority_tier_found': has_priority,
        'available_tier_found': has_available,
        'venv_found': venv_dir is not None,
        'venv_path': venv_dir,
        'bare_python_failures': bare_failures,
        'framework_docs': len(fw_files),
        'project_docs': len(proj_files),
        'total_docs': total_docs,
    }

    # --- Detect old system (list-docs calls) ---
    bash_cmds = _get_bash_commands(orchestrator)
    list_docs_calls = [cmd for cmd, _ in bash_cmds if 'list-docs' in cmd]
    details['list_docs_calls'] = len(list_docs_calls)

    # --- Verdict ---
    if not task_spawns:
        return NOT_EXERCISED, 'No Task tool spawns found', details

    if total_docs == 0:
        return NOT_EXERCISED, 'No docs available (no .md files in docs/ or input/docs/)', details

    # If old system was in use (list-docs called), tiered system wasn't active
    if spawns_with_docs == 0 and list_docs_calls:
        return NOT_EXERCISED, f'Old doc system in use (list-docs called {len(list_docs_calls)} time(s))', details

    issues = []
    if spawns_with_docs == 0:
        issues.append(f'Doc context not passed to subagents (0/{len(task_spawns)} spawns include tier markers)')
    if venv_dir and bare_failures and not list_docs_calls:
        issues.append(f'{len(bare_failures)} bare python/pip failure(s) despite venv at {venv_dir}/')

    if issues:
        return FAIL, '; '.join(issues), details

    parts = [f'{spawns_with_docs}/{len(task_spawns)} spawn(s) received doc context']
    if venv_dir:
        parts.append('no bare python/pip failures')
    parts.append(f'{total_docs} doc(s) available')
    return PASS, ', '.join(parts), details


# Fix validation registry — grouped by introduction phase.
# All entries always run (cumulative regression). Add new groups for future phases.
FIX_VALIDATIONS = [
    {
        'id': 'permission-spam',
        'group': 'phase-b',
        'name': 'Permission Auto-Approval',
        'description': 'PreToolUse hook auto-approves safe commands including chained (&&)',
        'check_fn': fix_permission_spam,
    },
    {
        'id': 'test-writer-alignment',
        'group': 'phase-b',
        'name': 'Test-Writer Alignment',
        'description': 'Test-writer receives task descriptions via phase-tasks for structural context',
        'check_fn': fix_test_writer_alignment,
    },
    {
        'id': 'cwd-stability',
        'group': 'phase-b',
        'name': 'CWD Stability',
        'description': 'story-files/phase-files use __file__-derived paths, immune to CWD drift',
        'check_fn': fix_cwd_stability,
    },
    {
        'id': 'context-exhaustion',
        'group': 'phase-b',
        'name': 'Context Budget',
        'description': 'Batch budget system prevents context window exhaustion',
        'check_fn': fix_context_exhaustion,
    },
    {
        'id': 'orphan-processes',
        'group': 'phase-b',
        'name': 'Process Cleanup',
        'description': 'PID tracking + cleanup hooks prevent orphaned background processes',
        'check_fn': fix_orphan_processes,
    },
    {
        'id': 'reference-docs',
        'group': 'phase-b',
        'name': 'Reference Docs',
        'description': 'list-docs command provides API documentation to implementers/test-writers',
        'check_fn': fix_reference_docs,
    },
    {
        'id': 'tiered-docs',
        'group': 'phase-c',
        'name': 'Tiered Doc System',
        'description': 'project-env.md passed to subagents with priority/available tiers, venv usage taught',
        'check_fn': fix_tiered_docs,
    },
]


def run_fix_validations(ctx):
    """Run all fix validations and return results grouped by introduction phase."""
    results = []
    for fv in FIX_VALIDATIONS:
        verdict, message, details = fv['check_fn'](ctx)
        results.append({
            'id': fv['id'],
            'group': fv['group'],
            'name': fv['name'],
            'description': fv['description'],
            'verdict': verdict,
            'message': message,
            'details': details,
        })
    return results


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def run_checks(conn, phase_id, project_root):
    """Run health checks and fix validations, return combined report."""
    log_dir = project_root / 'output' / 'logs'

    # Load log files
    events = _load_jsonl(log_dir / 'events.jsonl')
    hook_decisions = _load_jsonl(log_dir / 'hook-decisions.jsonl')
    orchestrator = _load_jsonl(log_dir / 'orchestrator.jsonl')

    # Get phase-scoped IDs
    story_ids, epic_ids = _get_phase_item_ids(conn, phase_id)
    task_ids = _get_phase_task_ids(conn, phase_id)

    # Filter events to this phase
    phase_events = _filter_events(events, task_ids, story_ids, phase_id)

    # Get phase status
    phase = conn.execute(
        'SELECT status, name FROM phases WHERE id = ?', (phase_id,)
    ).fetchone()

    # --- Health checks ---
    results = []
    checks = [
        ('Lifecycle Integrity', lambda: check_lifecycle(phase_events, task_ids)),
        ('Test-Writer Output', lambda: check_test_writer(project_root)),
        ('Permission Health', lambda: check_permissions(hook_decisions)),
        ('Error-Free Execution', lambda: check_error_free(orchestrator)),
        ('Story Gates', lambda: check_story_gates(conn, phase_id, story_ids)),
        ('Batch Counter', lambda: check_batch_counter(phase_events)),
        ('Process Cleanup', lambda: check_process_cleanup(project_root, orchestrator)),
        ('Compaction Health', lambda: check_compaction_health(events, orchestrator)),
    ]

    for name, check_fn in checks:
        verdict, message, details = check_fn()
        results.append({
            'check': name,
            'verdict': verdict,
            'message': message,
            'details': details,
        })

    # --- Fix validations (cumulative regression) ---
    ctx = {
        'hook_decisions': hook_decisions,
        'orchestrator': orchestrator,
        'events': events,
        'phase_events': phase_events,
        'project_root': project_root,
        'conn': conn,
        'phase_id': phase_id,
        'phase_status': phase['status'] if phase else 'unknown',
    }
    fix_results = run_fix_validations(ctx)

    return {
        'phase_id': phase_id,
        'phase_name': phase['name'] if phase else 'unknown',
        'phase_status': phase['status'] if phase else 'unknown',
        'checks': results,
        'summary': {
            'pass': sum(1 for r in results if r['verdict'] == PASS),
            'fail': sum(1 for r in results if r['verdict'] == FAIL),
            'not_exercised': sum(1 for r in results if r['verdict'] == NOT_EXERCISED),
        },
        'fix_validations': fix_results,
        'fix_summary': {
            'pass': sum(1 for r in fix_results if r['verdict'] == PASS),
            'fail': sum(1 for r in fix_results if r['verdict'] == FAIL),
            'not_exercised': sum(1 for r in fix_results if r['verdict'] == NOT_EXERCISED),
        },
    }


def print_human(report):
    """Print a human-readable report."""
    print(f'Phase: {report["phase_name"]} ({report["phase_id"]})')
    print(f'Phase status: {report["phase_status"]}')
    print()

    print('Health Checks:')
    for r in report['checks']:
        icon = {'PASS': '+', 'FAIL': '!', 'NOT_EXERCISED': '-'}[r['verdict']]
        print(f'  [{icon}] {r["check"]}: {r["verdict"]}')
        print(f'      {r["message"]}')

    # Fix validations grouped by introduction phase
    fix_results = report.get('fix_validations', [])
    if fix_results:
        groups = {}
        for r in fix_results:
            groups.setdefault(r['group'], []).append(r)
        for group, items in groups.items():
            print()
            print(f'Fix Validations ({group}):')
            for r in items:
                icon = {'PASS': '+', 'FAIL': '!', 'NOT_EXERCISED': '-'}[r['verdict']]
                print(f'  [{icon}] {r["name"]}: {r["verdict"]}')
                print(f'      {r["message"]}')

    print()
    s = report['summary']
    fs = report.get('fix_summary', {})
    health_str = f'{s["pass"]}P/{s["fail"]}F/{s["not_exercised"]}NE'
    if fs:
        fix_str = f'{fs["pass"]}P/{fs["fail"]}F/{fs["not_exercised"]}NE'
        print(f'Summary: {len(report["checks"])} health ({health_str}), {len(fix_results)} fix ({fix_str})')
    else:
        print(f'Summary: {s["pass"]} passed, {s["fail"]} failed, {s["not_exercised"]} not exercised')


# ---------------------------------------------------------------------------
# Auto-detect phase
# ---------------------------------------------------------------------------

def auto_detect_phase(conn):
    """Find the most relevant phase to validate.

    Priority: gate_pending > in_progress > complete (most recent) > tests_written.
    """
    for status in ('gate_pending', 'in_progress', 'complete', 'tests_written'):
        phase = conn.execute(
            'SELECT id FROM phases WHERE status = ? ORDER BY sequence DESC LIMIT 1',
            (status,)
        ).fetchone()
        if phase:
            return phase['id']
    return None


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='Validate a Clyde implementation phase'
    )
    parser.add_argument(
        'phase_id', nargs='?', default=None,
        help='Phase ID to validate (omit with --auto for auto-detection)'
    )
    parser.add_argument(
        '--auto', action='store_true',
        help='Auto-detect the most relevant phase'
    )
    parser.add_argument(
        '--json', action='store_true', dest='output_json',
        help='Output JSON instead of human-readable text'
    )
    parser.add_argument(
        '--project-root', default=str(Path(__file__).resolve().parent.parent),
        help='Project root directory (default: derived from script location)'
    )
    args = parser.parse_args()

    project_root = Path(args.project_root)
    db_path = project_root / 'output' / 'plan.db'
    if not db_path.exists():
        print(f'ERROR: {db_path} not found. Run the Intake Phase first.', file=sys.stderr)
        sys.exit(1)

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    # Determine phase
    phase_id = args.phase_id
    if args.auto or phase_id is None:
        phase_id = auto_detect_phase(conn)
        if phase_id is None:
            print('ERROR: No active or completed phase found. Specify a phase ID.', file=sys.stderr)
            sys.exit(1)

    # Verify phase exists
    phase = conn.execute('SELECT id FROM phases WHERE id = ?', (phase_id,)).fetchone()
    if not phase:
        print(f'ERROR: Phase {phase_id} not found in plan.db', file=sys.stderr)
        sys.exit(1)

    report = run_checks(conn, phase_id, project_root)
    conn.close()

    if args.output_json:
        print(json.dumps(report, indent=2))
    else:
        print_human(report)

    # Exit code: 0 if no failures, 1 if any FAIL (health or fix)
    total_fails = report['summary']['fail'] + report.get('fix_summary', {}).get('fail', 0)
    sys.exit(1 if total_fails > 0 else 0)
