"""Find decision-maker contacts at a company (founders, hiring managers, recruiters).

Order of providers tried:
  1. Hunter.io  (free tier 25 searches/mo) — domain-based email search
  2. Apollo.io  (optional fallback — TODO)
"""
import re
import time
import urllib.parse
from typing import Optional

import httpx

from . import profile as profile_mod

# Title keywords ranked by relevance for a job application.  Higher score = more
# likely to be the right contact to email cold.
TITLE_WEIGHTS: list[tuple[str, int]] = [
    (r"\b(founder|co[-\s]?founder)\b", 100),
    (r"\b(ceo|chief executive)\b", 95),
    (r"\b(cto|chief technology)\b", 90),
    (r"\bhead of (engineering|eng)\b", 85),
    (r"\bvp[\s,]+engineering\b", 80),
    (r"\b(engineering manager|eng manager)\b", 75),
    (r"\b(staff engineer)\b", 60),
    (r"\b(recruiter|talent partner|talent acquisition|technical recruiter)\b", 55),
    (r"\b(head of people|head of talent|hr lead|people ops)\b", 50),
    (r"\b(hiring manager)\b", 70),
]


def _domain_from_url(url: str) -> Optional[str]:
    try:
        host = urllib.parse.urlparse(url if "://" in url else f"https://{url}").netloc
        host = host.lower().lstrip("www.")
        if "." in host:
            return host
    except Exception:
        pass
    return None


def guess_domain(company: str, description: str = "") -> Optional[str]:
    """Best-effort: scan description for company URL, else slug + .com."""
    blocked = {
        "news.ycombinator.com", "linkedin.com", "twitter.com", "x.com",
        "github.com", "lever.co", "greenhouse.io", "ashbyhq.com",
        "workable.com", "wellfound.com", "ycombinator.com",
        "google.com", "youtube.com", "medium.com", "notion.so",
    }
    for m in re.finditer(r"https?://([^\s)\]>,'\"]+)", description or ""):
        host = _domain_from_url(m.group(0))
        if not host:
            continue
        if any(host.endswith(b) for b in blocked):
            continue
        return host

    if company:
        slug = re.sub(r"[^a-zA-Z0-9]", "", company).lower()
        if slug:
            return f"{slug}.com"
    return None


def _score_title(title: Optional[str]) -> int:
    if not title:
        return 0
    t = title.lower()
    for pat, score in TITLE_WEIGHTS:
        if re.search(pat, t):
            return score
    return 0


def hunter_domain_search(domain: str, *, api_key: Optional[str] = None,
                         limit: int = 10) -> list[dict]:
    api_key = api_key or profile_mod.api_key("hunter")
    if not api_key:
        return []
    url = "https://api.hunter.io/v2/domain-search"
    params = {"domain": domain, "limit": str(limit), "api_key": api_key}
    r = httpx.get(url, params=params, timeout=30)
    if r.status_code != 200:
        return []
    data = r.json().get("data", {})
    out = []
    for em in data.get("emails", []):
        first = em.get("first_name") or ""
        last = em.get("last_name") or ""
        name = (first + " " + last).strip() or None
        title = em.get("position")
        score = _score_title(title)
        if score == 0 and em.get("seniority") not in ("executive", "senior"):
            # skip noise
            continue
        out.append({
            "name": name,
            "title": title,
            "email": em.get("value"),
            "linkedin": (em.get("linkedin") or None),
            "confidence": max(em.get("confidence") or 0, score),
            "source": "hunter",
        })
    out.sort(key=lambda r: r["confidence"], reverse=True)
    return out


def find_contacts_for_job(job: dict) -> list[dict]:
    """High-level: try multiple providers, dedupe, rank."""
    domain = guess_domain(job.get("company", ""), job.get("description", ""))
    if not domain:
        return []
    seen = set()
    results = []
    for row in hunter_domain_search(domain):
        if row["email"] and row["email"] not in seen:
            seen.add(row["email"])
            results.append(row)
        time.sleep(0)  # keep linter happy; placeholder for rate-limit later
    return results
