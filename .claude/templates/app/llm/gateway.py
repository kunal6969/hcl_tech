# file: app/llm/gateway.py
"""Single entry point for every LLM call.

complete() walks the provider chain (LLM_PROVIDER, then LLM_FALLBACKS), honours MOCK_LLM,
retries 429/5xx with Retry-After-aware backoff, puts rate-limited providers in cooldown,
validates JSON against a Pydantic schema (one repair retry per provider), caches responses,
and returns an LLMResult with provider, model, tokens and latency for the trace.
"""
from __future__ import annotations

import hashlib
import json
import os
import random
import re
import sqlite3
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Literal

import httpx
from pydantic import BaseModel, ValidationError

Mode = Literal["fast", "deep"]
Message = dict[str, str]  # {"role": "system" | "user" | "assistant", "content": "..."}

REPAIR_PROMPT = (
    "Your previous reply was not valid for the required JSON schema.\n"
    "Error: {error}\n"
    "Reply again with ONLY the corrected JSON object. No prose, no markdown fences."
)


def _env(name: str, default: str = "") -> str:
    value = os.getenv(name)
    return default if value is None or value.strip() == "" else value.strip()


def _flag(name: str, default: bool = False) -> bool:
    return _env(name, "true" if default else "false").lower() in {"1", "true", "yes", "on"}


def provider_config(name: str) -> dict[str, Any]:
    """Provider table, rebuilt from env on every call so live switches and tests just work."""
    ollama = _env("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
    table: dict[str, dict[str, Any]] = {
        "gemini": {
            "style": "openai",
            "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
            "key": _env("GEMINI_API_KEY") or _env("GOOGLE_API_KEY"),
            "models": {"fast": _env("GEMINI_FAST_MODEL", "gemini-3.8-flash"),
                       "deep": _env("GEMINI_DEEP_MODEL", "gemini-3.8-flash")},
            "effort": {"fast": _env("GEMINI_FAST_EFFORT", "low"), "deep": _env("GEMINI_DEEP_EFFORT", "high")},
            "rpm": int(_env("GEMINI_RPM", "0")), "timeout": float(_env("GEMINI_TIMEOUT", "60")),
        },
        "groq": {
            "style": "openai",
            "base_url": "https://api.groq.com/openai/v1",
            "key": _env("GROQ_API_KEY"),
            "models": {"fast": _env("GROQ_FAST_MODEL", "openai/gpt-oss-20b"),
                       "deep": _env("GROQ_DEEP_MODEL", "openai/gpt-oss-120b")},
            "effort": {"fast": _env("GROQ_FAST_EFFORT", "low"), "deep": _env("GROQ_DEEP_EFFORT", "high")},
            "rpm": int(_env("GROQ_RPM", "0")), "timeout": float(_env("GROQ_TIMEOUT", "45")),
        },
        "ollama": {
            "style": "openai",
            "base_url": f"{ollama}/v1",
            "key": "ollama", "needs_key": False,
            "models": {"fast": _env("OLLAMA_MODEL", "qwen2.5:7b-instruct"),
                       "deep": _env("OLLAMA_DEEP_MODEL", _env("OLLAMA_MODEL", "qwen2.5:7b-instruct"))},
            "effort": {"fast": "none", "deep": "none"},
            "rpm": 0, "timeout": float(_env("OLLAMA_TIMEOUT", "180")),
        },
        "openai": {
            "style": "openai",
            "base_url": _env("OPENAI_BASE_URL", "https://api.openai.com/v1"),
            "key": _env("OPENAI_API_KEY"),
            "models": {"fast": _env("OPENAI_FAST_MODEL"), "deep": _env("OPENAI_DEEP_MODEL", _env("OPENAI_FAST_MODEL"))},
            "effort": {"fast": _env("OPENAI_FAST_EFFORT", "none"), "deep": _env("OPENAI_DEEP_EFFORT", "none")},
            "rpm": int(_env("OPENAI_RPM", "0")), "timeout": float(_env("OPENAI_TIMEOUT", "60")),
        },
        "anthropic": {
            "style": "anthropic",
            "base_url": "https://api.anthropic.com/v1",
            "key": _env("ANTHROPIC_API_KEY"),
            "models": {"fast": _env("ANTHROPIC_FAST_MODEL", "claude-haiku-5-5"),
                       "deep": _env("ANTHROPIC_DEEP_MODEL", "claude-sonnet-5-5")},
            "effort": {"fast": "none", "deep": "none"},
            "rpm": int(_env("ANTHROPIC_RPM", "0")), "timeout": float(_env("ANTHROPIC_TIMEOUT", "60")),
        },
    }
    key = name.lower()
    if key not in table:
        raise ValueError(f"Unknown LLM provider '{name}'. Options: {', '.join(table)}, mock")
    cfg = dict(table[key], name=key)
    cfg.setdefault("needs_key", True)
    if key == _env("LLM_PROVIDER", "gemini").lower() and _env("LLM_MODEL"):
        cfg["models"] = {"fast": _env("LLM_MODEL"), "deep": _env("LLM_MODEL")}
    return cfg


def provider_chain() -> list[str]:
    if _flag("MOCK_LLM"):
        return ["mock"]
    names = [_env("LLM_PROVIDER", "gemini")] + _env("LLM_FALLBACKS").split(",")
    chain: list[str] = []
    for name in (n.strip().lower() for n in names):
        if name and name not in chain:
            chain.append(name)
    return chain


@dataclass
class LLMResult:
    text: str = ""
    data: Any = None                  # validated Pydantic instance when schema= was given
    provider: str = "none"            # gemini | groq | ollama | openai | anthropic | mock | fallback | none
    model: str = ""
    mode: str = "fast"
    tokens_in: int = 0
    tokens_out: int = 0
    latency_ms: float = 0.0
    cache_hit: bool = False
    fallback_used: bool = False       # True when a deterministic fallback produced the output
    estimated_tokens: bool = False
    attempts: list[dict] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.data is not None or bool(self.text.strip())

    def usage(self) -> dict:
        return {"provider": self.provider, "model": self.model, "mode": self.mode,
                "tokens_in": self.tokens_in, "tokens_out": self.tokens_out,
                "latency_ms": round(self.latency_ms, 1), "cache_hit": self.cache_hit,
                "fallback_used": self.fallback_used, "llm_call": self.provider not in {"mock", "fallback", "none"}}

    def as_step(self, node: str, purpose: str = "") -> dict:
        return {"node": node, "tool": "llm", "status": "fallback" if self.fallback_used else "ok",
                "ms": round(self.latency_ms, 1), "input": {"purpose": purpose},
                "output": {**self.usage(), "attempts": self.attempts[-6:]}}


class LLMError(Exception):
    def __init__(self, kind: str, message: str, retry_after: float | None = None, status: int | None = None):
        super().__init__(message)
        self.kind, self.message, self.retry_after, self.status = kind, message, retry_after, status


def _retry_after(resp: httpx.Response) -> float | None:
    header = resp.headers.get("retry-after")
    if header:
        try:
            return float(header)
        except ValueError:
            pass
    body = resp.text
    m = re.search(r'"retryDelay"\s*:\s*"(\d+(?:\.\d+)?)s"', body)               # Gemini RetryInfo
    if m:
        return float(m.group(1))
    m = re.search(r"try again in (?:(\d+)m)?(\d+(?:\.\d+)?)(ms|s)\b", body, re.I)  # Groq message
    if m:
        seconds = float(m.group(2)) / (1000 if m.group(3).lower() == "ms" else 1)
        return seconds + 60 * int(m.group(1) or 0)
    return None


def _classify(resp: httpx.Response) -> LLMError:
    status = resp.status_code
    kind = ("rate_limit" if status == 429 else
            "server" if status in (500, 502, 503, 504, 529) else
            "auth" if status in (401, 403) else
            "not_found" if status == 404 else
            "timeout" if status == 408 else "bad_request")
    return LLMError(kind, resp.text[:600], retry_after=_retry_after(resp), status=status)


def _strip_reasoning(text: str) -> str:
    text = re.sub(r"<think>.*?</think>", "", text or "", flags=re.S | re.I)
    if "<think>" in text.lower():  # truncated reasoning block: keep whatever follows it
        text = text[text.lower().rfind("</think>") + 8:] if "</think>" in text.lower() else ""
    return text.strip()


def _extract_json(text: str) -> Any:
    t = _strip_reasoning(text)
    t = re.sub(r"^```(?:json)?\s*", "", t, flags=re.I)
    t = re.sub(r"\s*```\s*$", "", t)
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        pass
    starts = [i for i in (t.find("{"), t.find("[")) if i != -1]
    if not starts:
        raise ValueError("no JSON object found in model output")
    start = min(starts)
    opener, closer = t[start], "}" if t[start] == "{" else "]"
    depth, in_str, escaped = 0, False, False
    for i in range(start, len(t)):
        ch = t[i]
        if in_str:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == opener:
            depth += 1
        elif ch == closer:
            depth -= 1
            if depth == 0:
                return json.loads(re.sub(r",\s*([}\]])", r"\1", t[start:i + 1]))
    raise ValueError("unbalanced JSON in model output")


def _parse(text: str, schema: type[BaseModel]) -> tuple[BaseModel | None, str]:
    try:
        return schema.model_validate(_extract_json(text)), ""
    except (ValueError, ValidationError, json.JSONDecodeError) as err:
        return None, str(err)[:600]


def _with_schema(messages: list[Message], schema: type[BaseModel] | None) -> list[Message]:
    if schema is None:
        return list(messages)
    rule = ("Return ONLY one JSON object (no prose, no markdown fences) valid against this JSON Schema:\n"
            + json.dumps(schema.model_json_schema(), separators=(",", ":")))
    msgs = [dict(m) for m in messages]
    if msgs and msgs[0]["role"] == "system":
        msgs[0]["content"] = msgs[0]["content"] + "\n\n" + rule
    else:
        msgs.insert(0, {"role": "system", "content": rule})
    return msgs


class _Cache:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(path), check_same_thread=False)
        self._db.execute("CREATE TABLE IF NOT EXISTS llm_cache (k TEXT PRIMARY KEY, provider TEXT, "
                         "model TEXT, text TEXT, created REAL)")
        self._lock = threading.Lock()

    def get(self, key: str) -> str | None:
        with self._lock:
            row = self._db.execute("SELECT text FROM llm_cache WHERE k = ?", (key,)).fetchone()
        return row[0] if row else None

    def put(self, key: str, provider: str, model: str, text: str) -> None:
        with self._lock:
            self._db.execute("INSERT OR REPLACE INTO llm_cache VALUES (?, ?, ?, ?, ?)",
                             (key, provider, model, text, time.time()))
            self._db.commit()


def _cache_key(provider: str, model: str, mode: str, messages: list[Message], temperature: float,
               schema: type[BaseModel] | None) -> str:
    blob = json.dumps({"p": provider, "m": model, "mode": mode, "msgs": messages, "t": temperature,
                       "schema": schema.model_json_schema() if schema else None}, sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()


class LLMGateway:
    def __init__(self, transport: httpx.BaseTransport | None = None,
                 sleep: Callable[[float], None] = time.sleep):
        self._transport = transport          # tests pass httpx.MockTransport
        self._sleep = sleep
        self._cooldown: dict[str, float] = {}
        self._last_call: dict[str, float] = {}
        self._lock = threading.Lock()
        self._cache = _Cache(Path(_env("LLM_CACHE_PATH", "data/llm_cache.sqlite"))) if _flag("LLM_CACHE", True) else None

    # ------------------------------------------------------------------ public
    def complete(self, messages: list[Message], *, mode: Mode = "fast", schema: type[BaseModel] | None = None,
                 temperature: float = 0.0, max_tokens: int = 1500,
                 fallback: Callable[[], Any] | None = None, use_cache: bool = True) -> LLMResult:
        """Return the first valid answer from the chain; otherwise the deterministic fallback."""
        t0 = time.perf_counter()
        attempts: list[dict] = []
        msgs = _with_schema(messages, schema)
        for name in provider_chain():
            if name == "mock":
                return self._finish(self._fallback(fallback, schema, attempts, "MOCK_LLM"), t0, mode)
            try:
                cfg = provider_config(name)
            except ValueError as err:
                attempts.append({"provider": name, "status": "config_error", "detail": str(err)})
                continue
            if cfg["needs_key"] and not cfg["key"]:
                attempts.append({"provider": name, "status": "skipped_no_key"})
                continue
            model = cfg["models"][mode]
            if not model:
                attempts.append({"provider": name, "status": "skipped_no_model"})
                continue
            key = _cache_key(name, model, mode, msgs, temperature, schema)
            if self._cache and use_cache:
                cached = self._cache.get(key)
                if cached is not None:
                    data, _ = _parse(cached, schema) if schema else (None, "")
                    if schema is None or data is not None:
                        return self._finish(LLMResult(text=cached, data=data, provider=name, model=model,
                                                      cache_hit=True, attempts=attempts), t0, mode)
            seconds_left = self._cooldown.get(name, 0.0) - time.time()
            if seconds_left > 0:
                attempts.append({"provider": name, "status": "skipped_cooldown", "seconds_left": round(seconds_left, 1)})
                continue
            result = self._try_provider(cfg, model, mode, msgs, schema, temperature, max_tokens, attempts)
            if result is not None:
                if self._cache and use_cache:
                    self._cache.put(key, name, model, result.text)
                return self._finish(result, t0, mode)
        return self._finish(self._fallback(fallback, schema, attempts, "all_providers_failed"), t0, mode)

    def health(self) -> dict:
        """Readiness without spending tokens: keys present, Ollama reachable, cooldowns."""
        chain = provider_chain()
        out: dict[str, Any] = {"chain": chain, "mock": chain == ["mock"], "providers": {}}
        for name in chain:
            if name == "mock":
                continue
            try:
                cfg = provider_config(name)
            except ValueError as err:
                out["providers"][name] = {"error": str(err)}
                continue
            info: dict[str, Any] = {"fast_model": cfg["models"]["fast"], "deep_model": cfg["models"]["deep"],
                                    "key_present": bool(cfg["key"]) if cfg["needs_key"] else None,
                                    "cooldown_s": max(0.0, round(self._cooldown.get(name, 0.0) - time.time(), 1))}
            if name == "ollama":
                info["reachable"] = _ollama_up(cfg["base_url"])
            out["providers"][name] = info
        usable = [n for n, i in out["providers"].items()
                  if i.get("key_present") is not False and i.get("reachable", True) and "error" not in i]
        out["status"] = "ok" if out["mock"] or usable else "degraded"
        return out

    # ----------------------------------------------------------------- private
    def _try_provider(self, cfg, model, mode, msgs, schema, temperature, max_tokens, attempts) -> LLMResult | None:
        params = {"effort": cfg["effort"].get(mode, "none"), "json": schema is not None}
        conversation = list(msgs)
        repaired = False
        tokens_in = tokens_out = 0
        estimated = False
        retries = int(_env("LLM_MAX_RETRIES", "2"))
        transient = 0
        for _ in range(retries + 4):  # hard bound: transient retries + param downgrades + one repair
            self._pace(cfg)
            try:
                text, (t_in, t_out), _ms = self._call(cfg, model, conversation, temperature, max_tokens, params)
            except LLMError as err:
                attempts.append({"provider": cfg["name"], "model": model, "status": err.kind,
                                 "http": err.status, "detail": err.message[:160]})
                low = err.message.lower()
                if err.kind == "bad_request" and params["effort"] not in ("", "none") and "reason" in low:
                    params["effort"] = "none"
                    continue
                if err.kind == "bad_request" and params["json"] and ("response_format" in low or "json" in low):
                    params["json"] = False
                    continue
                if err.kind in {"rate_limit", "server", "timeout"}:
                    wait = err.retry_after if err.retry_after is not None else min(8.0, 2 ** transient + random.random())
                    if wait > float(_env("LLM_MAX_WAIT_S", "8")) or transient >= retries:
                        self._cooldown[cfg["name"]] = time.time() + max(wait, 15.0)
                        return None
                    transient += 1
                    self._sleep(wait)
                    continue
                return None  # auth / not_found / other bad_request: try the next provider
            if t_in is None or t_out is None:
                estimated = True
                t_in = sum(len(m["content"]) for m in conversation) // 4
                t_out = len(text) // 4
            tokens_in += t_in
            tokens_out += t_out
            text = _strip_reasoning(text)
            base = dict(provider=cfg["name"], model=model, tokens_in=tokens_in, tokens_out=tokens_out,
                        estimated_tokens=estimated, attempts=attempts)
            if schema is None:
                if text:
                    attempts.append({"provider": cfg["name"], "model": model, "status": "ok"})
                    return LLMResult(text=text, **base)
                attempts.append({"provider": cfg["name"], "model": model, "status": "empty_output"})
                return None
            data, error = _parse(text, schema)
            if data is not None:
                attempts.append({"provider": cfg["name"], "model": model, "status": "ok"})
                return LLMResult(text=text, data=data, **base)
            attempts.append({"provider": cfg["name"], "model": model, "status": "invalid_output", "detail": error[:160]})
            if repaired:
                return None
            repaired = True
            conversation = conversation + [{"role": "assistant", "content": text[:4000] or "(empty)"},
                                           {"role": "user", "content": REPAIR_PROMPT.format(error=error)}]
        return None

    def _call(self, cfg, model, messages, temperature, max_tokens, params):
        headers = {"Content-Type": "application/json"}
        if cfg["style"] == "openai":
            url = f"{cfg['base_url']}/chat/completions"
            headers["Authorization"] = f"Bearer {cfg['key']}"
            body: dict[str, Any] = {"model": model, "messages": messages,
                                    "temperature": temperature, "max_tokens": max_tokens}
            if params["effort"] not in ("", "none"):
                body["reasoning_effort"] = params["effort"]
            if params["json"]:
                body["response_format"] = {"type": "json_object"}
        else:  # anthropic messages API
            url = f"{cfg['base_url']}/messages"
            headers.update({"x-api-key": cfg["key"], "anthropic-version": "2023-06-01"})
            system = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
            body = {"model": model, "max_tokens": max_tokens, "temperature": temperature,
                    "messages": [m for m in messages if m["role"] != "system"]}
            if system:
                body["system"] = system
        t0 = time.perf_counter()
        try:
            with httpx.Client(timeout=cfg["timeout"], transport=self._transport) as client:
                resp = client.post(url, headers=headers, json=body)
        except httpx.TimeoutException as err:
            raise LLMError("timeout", f"timeout: {err}") from err
        except httpx.HTTPError as err:
            raise LLMError("server", f"connection: {err}") from err
        if resp.status_code >= 400:
            raise _classify(resp)
        payload = resp.json()
        usage = payload.get("usage") or {}
        if cfg["style"] == "openai":
            message = ((payload.get("choices") or [{}])[0].get("message") or {})
            text = message.get("content") or ""
            tokens = (usage.get("prompt_tokens"), usage.get("completion_tokens"))
        else:
            text = "".join(b.get("text", "") for b in payload.get("content", []) if b.get("type") == "text")
            tokens = (usage.get("input_tokens"), usage.get("output_tokens"))
        return text, tokens, (time.perf_counter() - t0) * 1000

    def _pace(self, cfg) -> None:
        rpm = cfg.get("rpm") or 0
        if rpm <= 0:
            return
        gap = 60.0 / rpm
        with self._lock:
            last = self._last_call.get(cfg["name"], 0.0)
            now = time.time()
            wait = last + gap - now
            self._last_call[cfg["name"]] = max(now, last + gap)
        if wait > 0:
            self._sleep(wait)

    @staticmethod
    def _fallback(fallback, schema, attempts, reason) -> LLMResult:
        attempts.append({"provider": "fallback", "status": reason})
        provider = "mock" if reason == "MOCK_LLM" else "fallback"
        if fallback is None:
            return LLMResult(provider="none", fallback_used=True, attempts=attempts)
        value = fallback()
        data = None
        if isinstance(value, BaseModel):
            data, text = value, value.model_dump_json()
        elif isinstance(value, dict) and schema is not None:
            data = schema.model_validate(value)
            text = data.model_dump_json()
        else:
            text = str(value)
        return LLMResult(text=text, data=data, provider=provider, model="deterministic-fallback",
                         fallback_used=True, attempts=attempts)

    @staticmethod
    def _finish(result: LLMResult, t0: float, mode: str) -> LLMResult:
        result.latency_ms = (time.perf_counter() - t0) * 1000
        result.mode = mode
        return result


def _ollama_up(base_url: str) -> bool:
    try:
        return httpx.get(base_url.removesuffix("/v1") + "/api/tags", timeout=2.0).status_code == 200
    except httpx.HTTPError:
        return False


def list_models(provider: str) -> list[str]:
    """IDs the provider currently serves — use at pre-flight to verify *_MODEL settings."""
    cfg = provider_config(provider)
    if cfg["style"] == "anthropic":
        headers = {"x-api-key": cfg["key"], "anthropic-version": "2023-06-01"}
    else:
        headers = {"Authorization": f"Bearer {cfg['key']}"}
    resp = httpx.get(f"{cfg['base_url']}/models", headers=headers, timeout=15.0)
    resp.raise_for_status()
    return sorted(str(m.get("id", "")).removeprefix("models/") for m in resp.json().get("data", []))


_GATEWAY: LLMGateway | None = None
_GATEWAY_LOCK = threading.Lock()


def get_gateway() -> LLMGateway:
    global _GATEWAY
    with _GATEWAY_LOCK:
        if _GATEWAY is None:
            _GATEWAY = LLMGateway()
        return _GATEWAY


def reset_gateway() -> None:
    """Call after changing env at runtime (tests, live provider switch from an admin endpoint)."""
    global _GATEWAY
    with _GATEWAY_LOCK:
        _GATEWAY = None
