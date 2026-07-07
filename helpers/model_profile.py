"""Runtime model profile — surfaces the signals a skill can use for version-aware
prompting (see skills/MODEL_CONVENTIONS.md).

Honesty note: the running Claude model's *identity* is NOT reliably exposed in the
environment. The harness sets no `CLAUDE_MODEL` variable. The authoritative branch
decision (Opus 4.8 vs legacy) is therefore made by the model itself, which knows
what it is — this module only reports the signals that ARE detectable, chiefly the
effort level, plus an optional self-reported model id a caller can pass in.

This is a display / effort-check helper. It does not gate behavior.
"""

from __future__ import annotations

import os
from typing import Optional


def effort() -> Optional[str]:
    """Return the configured effort level (CLAUDE_EFFORT), lowercased, or None.

    Values seen in practice: low, medium, high, xhigh, max.
    """
    val = os.environ.get("CLAUDE_EFFORT")
    return val.strip().lower() if val else None


def is_intelligence_effort() -> bool:
    """True if effort is in the high/xhigh/max band recommended for L3+ analysis.

    Returns True when effort is unset: an unset effort usually means a capable
    default, and a spurious "raise your effort" prompt is worse than staying quiet.
    Only low/medium return False — those are the cases worth flagging before an
    intelligence-sensitive analysis.
    """
    e = effort()
    if e is None:
        return True
    return e in {"high", "xhigh", "max"}


def describe(model_id: Optional[str] = None) -> str:
    """One-line, human-readable profile a skill can echo to the user.

    `model_id` is the model's self-reported id, passed in by the caller because the
    environment does not expose it. Without it, only effort is reported.
    """
    model_part = f"model={model_id}" if model_id else "model=self-reported (not in env)"
    e = effort()
    effort_part = f"effort={e}" if e else "effort=default"
    band = "intelligence-band (high+)" if is_intelligence_effort() else "scoped-band (low/medium)"
    return " · ".join([model_part, effort_part, band])
