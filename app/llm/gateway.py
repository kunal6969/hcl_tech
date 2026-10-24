"""
gateway.py — Single LLM gateway for the hospital assistant.

All LLM calls go through call_llm(). Never call an LLM directly from a node.

Provider chain: Groq (main) -> Gemini Flash (fallback).
MOCK_LLM=true: returns deterministic canned responses for offline tests.

SDKs:
  groq >= 1.7      — Groq(api_key=).chat.completions.create(...)
  google-genai >= 2 — google.genai.Client(api_key=).models.generate_content(...)
"""
from __future__ import annotations

import json
import os
import time
from typing import Any

# Map old/removed Gemini model names to current ones
_GEMINI_MODEL_ALIASES: dict[str, str] = {
    "gemini-2.0-flash": "gemini-3.8-flash",
    "gemini-1.5-flash": "gemini-3.8-flash",
    "gemini-1.5-pro": "gemini-3.8-flash",
}

# ---------------------------------------------------------------------------
# MOCK responses — keyed by the first word of the system prompt
# These let tests run fully offline (MOCK_LLM=true)
# ---------------------------------------------------------------------------
_MOCK_ROUTER_RESPONSE = {
    "intent": "policy_fact",
    "params": {},
    "confidence": 1.0,
}

_MOCK_COMPOSE_RESPONSE = {
    "answer": "This is a mock answer for testing.",
    "explanation": "Mock LLM response.",
    "assumptions": [],
}

MOCK_RESPONSES: dict[str, Any] = {
    "router": _MOCK_ROUTER_RESPONSE,
    "compose": _MOCK_COMPOSE_RESPONSE,
}


def _is_mock() -> bool:
    """Return True when MOCK_LLM env var is set to a truthy value."""
    return os.getenv("MOCK_LLM", "false").lower() in ("1", "true", "yes")


def call_llm(
    system_prompt: str,
    user_message: str,
    mode: str = "compose",
    schema: dict | None = None,
    temperature: float = 0.0,
) -> dict[str, Any]:
    """
    Call the LLM with structured JSON output.
    Provider chain: Groq -> Gemini. MOCK_LLM=true returns canned responses.
    """
    print(f"[GATEWAY] call_llm | mode={mode} | mock={_is_mock()} | msg_len={len(user_message)}")

    if _is_mock():
        resp = dict(MOCK_RESPONSES.get(mode, MOCK_RESPONSES["compose"]))
        print(f"[GATEWAY] MOCK response | keys={list(resp.keys())}")
        return resp

    start = time.monotonic()
    result, model_used, error = None, "none", None

    # --- Try Groq first ---
    print("[GATEWAY] Trying Groq ...")
    try:
        result, model_used = _call_groq(system_prompt, user_message, temperature)
        print(f"[GATEWAY] Groq OK | model={model_used} | len={len(result)}")
    except Exception as e:
        error = f"groq: {e}"
        print(f"[GATEWAY] Groq FAILED: {e}")

    # --- Fallback to Gemini ---
    if result is None:
        print("[GATEWAY] Trying Gemini fallback ...")
        try:
            result, model_used = _call_gemini(system_prompt, user_message, temperature)
            error = None
            print(f"[GATEWAY] Gemini OK | model={model_used} | len={len(result)}")
        except Exception as e2:
            error = f"{error} | gemini: {e2}"
            print(f"[GATEWAY] Gemini FAILED: {e2}")

    if result is None:
        print(f"[GATEWAY] ALL providers failed: {error}")
        raise RuntimeError(f"All LLM providers failed: {error}")

    latency_ms = (time.monotonic() - start) * 1000
    print(f"[GATEWAY] Done | model={model_used} | latency={latency_ms:.0f}ms")

    parsed = _parse_json(result)
    parsed["_meta"] = {"model": model_used, "latency_ms": round(latency_ms, 1)}
    return parsed


# ---------------------------------------------------------------------------
# Provider: Groq (groq >= 1.7)
# ---------------------------------------------------------------------------

_GROQ_FALLBACK_MODELS = ["openai/gpt-oss-20b", "qwen/qwen3.8-27b", "openai/gpt-oss-120b"]


def _call_groq(system_prompt: str, user_message: str, temperature: float) -> tuple[str, str]:
    """Call Groq API via the groq SDK. Returns (raw_text, model_id)."""
    from groq import Groq

    api_key = os.getenv("GROQ_API_KEY")
    print(f"[GROQ] key_present={bool(api_key)} | starts_gsk={str(api_key or '').startswith('gsk_')}")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY not set")

    env_model = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")
    models_to_try = [env_model] + [m for m in _GROQ_FALLBACK_MODELS if m != env_model]

    client = Groq(api_key=api_key)

    last_err = None
    for model in models_to_try:
        try:
            print(f"[GROQ] Trying model={model}")
            resp = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ],
                temperature=temperature,
                response_format={"type": "json_object"},
                max_completion_tokens=1024,
            )
            content = resp.choices[0].message.content
            tokens = resp.usage.total_tokens if resp.usage else "n/a"
            print(f"[GROQ] OK | model={model} | tokens={tokens}")
            return content, model
        except Exception as e:
            last_err = e
            print(f"[GROQ] model={model} failed: {e}")
            if "model" not in str(e).lower() and "404" not in str(e):
                raise
    raise last_err  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Provider: Google Gemini (google-genai >= 2.0)
# ---------------------------------------------------------------------------

def _call_gemini(system_prompt: str, user_message: str, temperature: float) -> tuple[str, str]:
    """Call Gemini via the google-genai SDK. Returns (raw_text, model_id)."""
    from google import genai
    from google.genai import types

    api_key = os.getenv("GEMINI_API_KEY")
    print(f"[GEMINI] key_present={bool(api_key)}")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not set")

    raw_model = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
    model_name = _GEMINI_MODEL_ALIASES.get(raw_model, raw_model)
    if model_name != raw_model:
        print(f"[GEMINI] Model alias: {raw_model} -> {model_name}")
    print(f"[GEMINI] model={model_name}")

    client = genai.Client(api_key=api_key)
    resp = client.models.generate_content(
        model=model_name,
        contents=user_message,
        config=types.GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=temperature,
            response_mime_type="application/json",
            max_output_tokens=1024,
        ),
    )
    text = resp.text or ""
    print(f"[GEMINI] Response OK | len={len(text)}")
    return text, model_name


# ---------------------------------------------------------------------------
# JSON parsing helper
# ---------------------------------------------------------------------------

def _parse_json(raw: str) -> dict[str, Any]:
    """Parse JSON from LLM response. Strips markdown fences, one repair retry."""
    print(f"[PARSE] raw[:80]={raw[:80]!r}")
    raw = raw.strip()

    if raw.startswith("```"):
        lines = raw.split("\n")
        raw = "\n".join(lines[1:-1] if lines[-1] == "```" else lines[1:])
        print("[PARSE] Stripped markdown fence")

    try:
        result = json.loads(raw)
        print(f"[PARSE] OK | keys={list(result.keys())}")
        return result
    except json.JSONDecodeError as e:
        print(f"[PARSE] Direct failed: {e}")

    start = raw.find("{")
    end = raw.rfind("}")
    if start != -1 and end != -1:
        try:
            result = json.loads(raw[start:end + 1])
            print(f"[PARSE] Repair OK | keys={list(result.keys())}")
            return result
        except json.JSONDecodeError as e2:
            print(f"[PARSE] Repair failed: {e2}")

    print("[PARSE] All attempts failed — returning error fallback")
    return {"_parse_error": True, "raw": raw[:200]}
