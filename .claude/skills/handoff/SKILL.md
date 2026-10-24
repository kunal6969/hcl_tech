---
name: handoff
description: Snapshots the build into HANDOFF_STATE.md and PROGRESS_LOG.md - tests run, work committed, exact next actions - so a fresh session (another teammate, another Claude account or laptop, or a new session after a usage limit, /clear or compaction) continues with zero rediscovery. Use when the user says handoff, hand over, switch account, switching laptop, pass to teammate, out of usage, limit reached, rate limited, save state, wrap up, lunch break, or before code freeze; also use proactively after a stage gate or when the conversation has grown long.
argument-hint: "[reason]"
effort: low
---

# Handoff (≤ 3 minutes)

Goal: someone who reads only HANDOFF_STATE.md can continue in under two minutes, on any account.

1. **Verify**: `pytest -q` (record passed/total; fix only one-liners now) and `git status --short`.
2. **Commit everything**: `git add -A && git commit -m "wip(handoff): <stage> <one-line summary>"` — even when
   red (say so in the message). If tests are green, this hash becomes `last_green_commit`.
3. **Rewrite HANDOFF_STATE.md in place** (keep every section of the template; ≤ 120 lines, ≤ ~6,000 chars,
   so the SessionStart hook can inject it whole):
   - `status`, `updated_utc` (`date -u +%FT%TZ`), `updated_by` (`git config user.name`), reason: $ARGUMENTS
   - **Next 3 actions**: exact and executable — file, function, command, expected result.
   - Stage board, requirement coverage, key decisions (one line each), open issues with the first three
     lines of each failing test's error, eval scoreboard, gotchas a fresh session must not rediscover,
     config notes (env var names and provider chain — never values).
4. **Append** one PROGRESS_LOG.md line: `<UTC> | <stage> | HANDOFF (<reason>) | <hash> | <passed>/<total> | <next action>`.
5. `git add HANDOFF_STATE.md PROGRESS_LOG.md && git commit -m "chore(handoff): state snapshot"`.
6. Next session on another machine? Ask the user before `git push` (never force).
7. **Print the resume card**:

```
Handoff saved at <hash> (<stage>, tests <passed>/<total>).
Next session: open this repo in Claude Code (git pull first if on another machine) and type /resume.
It will start with: <next action 1>.
```

8. If the user is continuing in **this** session, suggest `/clear` now: the state file replaces the whole
   conversation, which keeps the remaining credits for the build rather than for re-reading history.


Quality bar: not "continue the refund work" but "implement fee waiver in app/tools/refunds.py::calculate_refund
so tests/test_refunds.py::test_gold_fee_waived passes (expected refund 2939.00, clause RET-POL#5.2)".
