# DECISIONS

## D1: X-Patient-Id + X-Role headers (not JWT)
- Reason: Simplest trusted context for a hackathon. JWT noted as production upgrade in README.
- Trade-off: No cryptographic proof of identity, but the demo environment is internal.

## D2: Groq main, Gemini flash fallback (not OpenAI)
- Reason: Free tier, fast inference, no cost risk. Statement doesn't mandate a provider.
- Disclosure: README will state: "Primary: Groq llama-3.3-70b-versatile. Fallback: Google Gemini Flash."

## D3: Keyword-first router, LLM fallback
- Reason: Saves LLM quota, fully deterministic for the common cases (appointments, labs, insurance).
- Fallback threshold: if keyword rules match no intent, call LLM with structured output.

## D4: One-step reschedule (no two-step confirmation)
- Reason: Simpler demo; valid date + slot → immediate action_completed. Invalid → refused with alternatives.
- Trade-off: Less human-in-the-loop. Noted in README as a production enhancement.

## D5: Conflict tie-break = newest ingested
- Reason: For the demo, admins upload newer docs to supersede old ones. Newest ingested wins.
- conflict_flagged is still returned when two chunks with identical authority+version+date+ingest_at disagree.

## D6: Core 4 tools + reschedule (no billing tool in MVP)
- Reason: Billing requires a procedure-cost table not in the spec. Mention as future work.

## D7: SQLite for all structured data (not DuckDB or Postgres)
- Reason: One file, zero setup, fully portable for judges. All queries are simple lookups.

## D8: Tier 1 fixed graph (not supervisor or planner)
- Reason: All intent routes are known at design time. A fixed graph is simpler, testable, and explainable.
  The judges' design principle explicitly says "simplest architecture wins."
