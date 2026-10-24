---
name: resume
description: Hydrates a fresh Claude Code session from HANDOFF_STATE.md, PROGRESS_LOG.md, git history and a quick test run, reconciles any drift between the notes and reality, then continues the autopilot exactly where the previous session, teammate or account stopped. Use at the start of any session whose HANDOFF_STATE.md status is PREFLIGHT, STAGE_n or FROZEN, and whenever the user says resume, continue, carry on, pick up, where were we, I'm back, new account, switched laptop, or after /clear or compaction.
effort: low
---

# Resume (≤ 3 minutes, then straight back to work)

1. **Hydrate.** The SessionStart hook already printed HANDOFF_STATE.md, the PROGRESS_LOG tail and git
   status. If that output is missing or was truncated, read HANDOFF_STATE.md. Then read only
   docs/REQUIREMENTS.md §3–4 (contract + traceability matrix) and the top of docs/ARCHITECTURE.md.
2. **Verify reality, not the note.**
   - `git log --oneline -10` and `git status --short`
   - remote configured and tree clean → `git pull --ff-only`
   - `pytest -q` (offline: MOCK_LLM, hash embeddings)
   - stage ≥ S4 → start the API (`uvicorn app.api.main:app --port 8000`) and `curl -s localhost:8000/health`
3. **Reconcile.** If the note disagrees with git or tests, trust git + tests, correct HANDOFF_STATE.md and
   log `RESUME: state corrected — <what>` in PROGRESS_LOG.md.
4. **Identity.** `git config user.name` — if another teammate is now driving, commits must carry their name.
5. **Report in ≤ 6 lines**: stage, last green commit, failing tests, next action, time left to freeze.
6. **Continue immediately** with "Next 3 actions" through skill `00-autopilot-orchestrator`'s loop. Don't
   repeat the pre-flight interview; re-plan only if the architecture is undecided or the user changed scope.
7. Status `FROZEN` → only docs, deliverables and demo prep; code stays at tag `final`.
