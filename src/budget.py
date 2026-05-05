"""Daily spend tracker. Stops API calls once the day's USD budget is exhausted."""
import json
from datetime import date
from pathlib import Path

LEDGER = Path(__file__).resolve().parent.parent / "data" / "spend_ledger.json"


class BudgetExceeded(Exception):
    pass


def _load() -> dict:
    if not LEDGER.exists():
        return {}
    return json.loads(LEDGER.read_text(encoding="utf-8"))


def _save(d: dict):
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    LEDGER.write_text(json.dumps(d, indent=2), encoding="utf-8")


def today_spent_usd() -> float:
    return float(_load().get(date.today().isoformat(), 0.0))


def remaining_usd(daily_cap: float) -> float:
    return max(0.0, daily_cap - today_spent_usd())


def check(daily_cap: float):
    if today_spent_usd() >= daily_cap:
        raise BudgetExceeded(
            f"Daily budget ${daily_cap:.2f} reached "
            f"(spent ${today_spent_usd():.4f}). Resets at midnight."
        )


def record(input_tokens: int, output_tokens: int, in_per_mtok: float, out_per_mtok: float) -> float:
    cost = (input_tokens * in_per_mtok + output_tokens * out_per_mtok) / 1_000_000
    d = _load()
    today = date.today().isoformat()
    d[today] = round(d.get(today, 0.0) + cost, 6)
    _save(d)
    return cost
