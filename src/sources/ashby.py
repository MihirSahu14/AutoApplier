"""Ashby public job-board scraper.

Endpoint per company:
  https://api.ashbyhq.com/posting-api/job-board/<slug>?includeCompensation=true
"""
from typing import Iterable
import httpx
from bs4 import BeautifulSoup

BASE = "https://api.ashbyhq.com/posting-api/job-board/{slug}?includeCompensation=true"


def _clean_html(html: str) -> str:
    if not html:
        return ""
    return BeautifulSoup(html, "lxml").get_text("\n", strip=True)


def fetch_company(slug: str) -> list[dict]:
    r = httpx.get(BASE.format(slug=slug), timeout=30)
    if r.status_code != 200:
        return []
    data = r.json()
    jobs = data.get("jobs", []) or []
    out = []
    for j in jobs:
        location = (j.get("location") or "").strip() or (
            ", ".join(filter(None, [j.get("locationName"), j.get("locationCountryCode")])) or ""
        )
        desc = _clean_html(j.get("descriptionHtml") or "") or j.get("descriptionPlain") or ""
        url = j.get("jobUrl") or j.get("applyUrl") or ""
        out.append({
            "source_id": f"{slug}:{j.get('id') or j.get('jobPostingId')}",
            "company": slug.replace("-", " ").title(),
            "title": j.get("title", ""),
            "location": location,
            "url": url,
            "description": desc,
            "posted_at": j.get("publishedAt"),
        })
    return out


def fetch(slugs: Iterable[str]) -> list[dict]:
    rows = []
    for s in slugs:
        try:
            rows.extend(fetch_company(s))
        except Exception as e:
            print(f"[ashby] {s} failed: {e}")
    return rows
