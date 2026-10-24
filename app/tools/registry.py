# file: app/tools/registry.py
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable

from pydantic import BaseModel, ValidationError


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str                      # one line; shown to the planner LLM
    input_model: type[BaseModel]
    fn: Callable[[Any, "ToolContext"], Any]
    needs_identity: bool = False          # personal data: refuse when no principal
    mutates_state: bool = False           # must be idempotent and re-check eligibility itself


@dataclass
class ToolContext:
    run_id: str
    principal: dict = field(default_factory=dict)
    as_of: Any = None
    config: dict = field(default_factory=dict)   # LangGraph "configurable" (top_k, scenario, ...)


REGISTRY: dict[str, ToolSpec] = {}


def register(spec: ToolSpec) -> ToolSpec:
    REGISTRY[spec.name] = spec
    return spec


def tool_catalog() -> str:
    lines = []
    for spec in REGISTRY.values():
        fields = ", ".join(
            f"{name}: {getattr(f.annotation, '__name__', str(f.annotation))}"
            + ("" if f.is_required() else " (optional)")
            for name, f in spec.input_model.model_fields.items())
        lines.append(f"- {spec.name}({fields}): {spec.description}")
    return "\n".join(lines)


def run_tool(name: str, raw_args: dict, ctx: ToolContext) -> dict:
    """Validate, authorise, execute. Returns a trace step and never raises."""
    t0 = time.perf_counter()
    spec = REGISTRY.get(name)
    status, output = "ok", None
    if spec is None:
        status, output = "error", {"error": "unknown_tool"}
    elif spec.needs_identity and not ctx.principal.get("subject_id"):
        status, output = "refused", {"error": "identity_required"}
    else:
        try:
            args = spec.input_model.model_validate(raw_args)
            result = spec.fn(args, ctx)
            output = result.model_dump(mode="json") if isinstance(result, BaseModel) else result
        except ValidationError as err:
            status = "error"
            output = {"error": "invalid_args",
                      "detail": [{"loc": list(e["loc"]), "msg": e["msg"]} for e in err.errors()]}
        except PermissionError:
            status, output = "refused", {"error": "not_authorised"}
        except LookupError as err:
            status, output = "error", {"error": "not_found", "detail": str(err)[:200]}
        except Exception as err:  # a tool bug must not crash the request; it shows up in the trace
            status, output = "error", {"error": type(err).__name__, "detail": str(err)[:300]}
    return {"node": "execute", "tool": name, "input": raw_args, "output": output, "status": status,
            "ms": round((time.perf_counter() - t0) * 1000, 2)}
