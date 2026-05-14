"""Per-user profile (contact info, targets, resume, API keys).

Stored at `data/profile.json`. Gitignored.  Replaces the profile/targets/visa
sections of `config.yaml` so the same code runs for anyone.

`config.yaml` is now app-level only (model names, pricing, budget caps, sources).
"""
import json
import os
from pathlib import Path
from typing import Optional

from .paths import PROFILE_PATH

DEFAULT_DISQUALIFIERS = [
    "us citizen required",
    "us citizenship required",
    "active security clearance",
    "public trust clearance",
    "no sponsorship",
    "will not sponsor",
    "cannot sponsor",
]


def empty_profile() -> dict:
    return {
        "contact": {
            "name": "", "email": "", "phone": "",
            "linkedin": "", "github": "", "portfolio": "",
            "location": "",
        },
        "experience_summary": "",
        "resume_pdf": "",
        "visa": {
            "status": "",
            "needs_sponsorship": False,
            "disqualify_if": DEFAULT_DISQUALIFIERS.copy(),
        },
        "targets": {
            "roles": [],
            "company_size_min": 0,
            "company_size_max": 100000,
            "locations_ok": ["united states", "usa", "remote (us)"],
            "locations_preferred": [],
            "salary_min_usd": 0,
        },
        "api_keys": {
            "anthropic": "", "hunter": "", "apollo": "", "serpapi": "",
        },
    }


def load() -> dict:
    if not PROFILE_PATH.exists():
        return empty_profile()
    saved = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
    # merge with defaults so older profiles keep working when we add fields
    base = empty_profile()
    for k, v in saved.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            base[k].update(v)
        else:
            base[k] = v
    return base


def save(p: dict) -> None:
    PROFILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    PROFILE_PATH.write_text(json.dumps(p, indent=2), encoding="utf-8")


def is_configured() -> bool:
    p = load()
    has_identity = bool(p["contact"]["name"] and p["contact"]["email"])
    has_background = bool(p.get("resume_pdf") or p.get("experience_summary"))
    has_key = bool(p["api_keys"].get("anthropic") or os.environ.get("ANTHROPIC_API_KEY"))
    return has_identity and has_background and has_key


def anthropic_key() -> Optional[str]:
    return load()["api_keys"].get("anthropic") or os.environ.get("ANTHROPIC_API_KEY") or None


def api_key(name: str) -> Optional[str]:
    return load()["api_keys"].get(name) or os.environ.get(f"{name.upper()}_API_KEY") or None


def candidate_text(p: Optional[dict] = None) -> str:
    """Resume PDF text if available, else the free-form experience summary."""
    from . import resume as resume_mod
    p = p or load()
    pdf = p.get("resume_pdf") or ""
    if pdf and Path(pdf).exists():
        return resume_mod.extract_text(pdf)
    return p.get("experience_summary") or ""


def build_profile_block(p: Optional[dict] = None, candidate: Optional[str] = None) -> str:
    """Render the structured profile + background text used in every Claude call."""
    p = p or load()
    if candidate is None:
        candidate = candidate_text(p)

    t = p["targets"]; v = p["visa"]; c = p["contact"]
    parts = [f"Name: {c.get('name', '')}"]
    if v.get("status"):
        parts.append(f"Visa: {v['status']}; needs sponsorship: {v.get('needs_sponsorship', False)}")
    if t.get("roles"):
        parts.append(f"Target roles: {', '.join(t['roles'])}")
    if t.get("company_size_min") is not None or t.get("company_size_max") is not None:
        parts.append(
            f"Company size preference: {t.get('company_size_min', 0)}-"
            f"{t.get('company_size_max', 100000)} employees"
        )
    if t.get("locations_ok"):
        parts.append(f"Locations OK: {', '.join(t['locations_ok'])}")
    if t.get("locations_preferred"):
        parts.append(f"Preferred locations: {', '.join(t['locations_preferred'])}")
    if t.get("salary_min_usd"):
        parts.append(f"Salary floor: ${t['salary_min_usd']:,}")
    if v.get("disqualify_if"):
        parts.append(f"Disqualifiers: {', '.join(v['disqualify_if'])}")
    parts.append("")
    if candidate:
        if (p.get("resume_pdf") and Path(p["resume_pdf"]).exists()):
            parts.append("Resume text:")
        else:
            parts.append("Background description (no formal resume):")
        parts.append(candidate)
    return "\n".join(parts)


def render_header_from_profile(p: Optional[dict] = None) -> dict:
    p = p or load()
    c = p["contact"]
    links = []
    if c.get("linkedin"):  links.append({"label": "LinkedIn",  "url": c["linkedin"]})
    if c.get("github"):    links.append({"label": "GitHub",    "url": c["github"]})
    if c.get("portfolio"): links.append({"label": "Portfolio", "url": c["portfolio"]})
    return {
        "name": c.get("name", ""),
        "location": c.get("location", ""),
        "phone": c.get("phone", ""),
        "email": c.get("email", ""),
        "links": links,
    }
