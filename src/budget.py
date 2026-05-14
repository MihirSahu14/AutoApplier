"""Per-stage daily spend tracker.

Ledger format (`data/spend_ledger.json`):
    {
      "2026-05-05": {"scoring": 0.27, "tailoring": 0.10, "outreach": 0.0}
    }

Each stage has its own cap (config.budget.stage_caps); the sum of caps is the
effective daily cap. Stages that hit their cap raise BudgetExceeded; other
stages keep working.
"""
import json
from datetime import date
from pathlib import Path

from .paths import LEDGER_PATH as LEDGER


class BudgetExceeded(Exception):
    pass


def _load() -> dict:
    if not LEDGER.exists():
        return {}
    raw = json.loads(LEDGER.read_text(encoding="utf-8"))
    # migrate old flat format ({date: float}) -> per-stage
    out = {}
    for k, v in raw.items():
        if isinstance(v, (int, float)):
            out[k] = {"scoring": float(v)}
        else:
            out[k] = v
    return out


def _save(d: dict):
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    LEDGER.write_text(json.dumps(d, indent=2), encoding="utf-8")


def _today() -> dict:
    return _load().get(date.today().isoformat(), {})


def stage_spent_usd(stage: str) -> float:
    return float(_today().get(stage, 0.0))


def today_spent_usd() -> float:
    return float(sum(_today().values()))


def stage_remaining_usd(stage: str, stage_caps: dict) -> float:
    cap = stage_caps.get(stage, 0.0)
    return max(0.0, cap - stage_spent_usd(stage))


def check(stage: str, stage_caps: dict):
    cap = stage_caps.get(stage, 0.0)
    spent = stage_spent_usd(stage)
    if spent >= cap:
        raise BudgetExceeded(
            f"{stage} budget ${cap:.2f} reached "
            f"(spent ${spent:.4f}). Resets at midnight."
        )


def record(stage: str, model: str, input_tokens: int, output_tokens: int,
           pricing: dict) -> float:
    p = pricing.get(model)
    if not p:
        raise ValueError(f"No pricing configured for model {model!r}")
    cost = (input_tokens * p["input"] + output_tokens * p["output"]) / 1_000_000
    d = _load()
    today = date.today().isoformat()
    day = d.setdefault(today, {})
    day[stage] = round(day.get(stage, 0.0) + cost, 6)
    _save(d)
    return cost
