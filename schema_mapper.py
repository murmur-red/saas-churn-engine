"""AI-assisted schema mapping — suggest `our_field: their_column` from a customer's columns.

This is an OPTIONAL ONBOARDING helper, NOT part of the churn calculation. The churn engine stays
deterministic and LLM-free; the AI only *proposes* a mapping you review/edit before the deterministic
engine runs. Suggestions are CONSTRAINED to real target fields (from the signal registry + core
identity fields) and validated by a deterministic critic — any hallucinated target or unknown source
column is dropped, so the AI can only ever pick fields the engine understands.

The LLM call is isolated behind `llm=`, so target discovery and the critic are testable without an API.
"""
from __future__ import annotations

import json
import os
from typing import Any, Callable, Optional

from signals import REGISTRY

# Identity / commercial fields the engine reads beyond the signals themselves.
CORE_TARGETS = [
    "account_name", "segment", "booked_arr", "renewal_date", "contract_start", "seats_licensed",
    "account_owner", "weekly_usage_series", "prior_period_arr", "expansion_arr", "contraction_arr",
    "churned_arr",
]


def target_fields() -> list[str]:
    """All fields we can map INTO: core identity + each signal's data field (deduped, sorted)."""
    return sorted({*CORE_TARGETS, *(s.field for s in REGISTRY)})


def _target_catalog() -> str:
    """Human-readable target list with signal labels, for the model's context."""
    label = {s.field: s.label for s in REGISTRY}
    lines = [f"- {f}" + (f"  ({label[f]})" if f in label else "") for f in target_fields()]
    return "\n".join(lines)


SYSTEM = """\
You map a customer's source column names onto a fixed target schema for a churn engine. You are given
the TARGET fields (with meanings) and the customer's SOURCE columns (with a few sample values). Return
the best `target: source_column` mapping.

Rules:
- Use ONLY target field names from the provided list; never invent a target.
- Map a target only when a source column clearly corresponds; leave unclear ones out.
- Each source column maps to at most one target.
- Output STRICT JSON only: {"mapping": {"<target>": "<source_column>", ...}}
"""


def _default_llm(prompt: str, model: str, api_key: str = "") -> str:
    import anthropic
    key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        raise RuntimeError("No Anthropic API key — provide your own key to auto-map with AI.")
    client = anthropic.Anthropic(api_key=key)
    kwargs = dict(model=model, max_tokens=2000,
                  system=[{"type": "text", "text": SYSTEM, "cache_control": {"type": "ephemeral"}}],
                  messages=[{"role": "user", "content": prompt}])
    try:
        resp = client.messages.create(temperature=0, **kwargs)
    except anthropic.BadRequestError as e:
        if "temperature" in str(e).lower():
            resp = client.messages.create(**kwargs)
        else:
            raise
    return "".join(b.text for b in resp.content if getattr(b, "type", None) == "text").strip()


def suggest_mapping(source_columns: list[str], sample_rows: Optional[list[dict]] = None,
                    model: str = "claude-sonnet-5", llm: Optional[Callable[[str, str], str]] = None,
                    api_key: str = "") -> dict[str, Any]:
    """Returns {'mapping': {our_field: their_column}, 'unmapped_sources': [...], 'targets': [...]}.
    The mapping is validated: only real target fields + real source columns survive."""
    targets = set(target_fields())
    samples = ""
    if sample_rows:
        samples = "\nSAMPLE VALUES (first rows):\n" + json.dumps(sample_rows[:3], default=str)
    prompt = (f"TARGET FIELDS:\n{_target_catalog()}\n\nSOURCE COLUMNS:\n"
              + ", ".join(source_columns) + samples + "\n\nReturn the mapping JSON.")

    text = (llm or (lambda p, m: _default_llm(p, m, api_key)))(prompt, model)
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    try:
        raw = json.loads(text.strip()).get("mapping", {})
    except (json.JSONDecodeError, AttributeError):
        raw = {}

    # Deterministic critic: keep only real targets + real source columns; one source per target.
    src = set(source_columns)
    used_sources: set[str] = set()
    mapping: dict[str, str] = {}
    for tgt, col in raw.items():
        if tgt in targets and col in src and col not in used_sources:
            mapping[tgt] = col
            used_sources.add(col)

    return {"mapping": mapping,
            "unmapped_sources": [c for c in source_columns if c not in used_sources],
            "targets": sorted(targets)}
