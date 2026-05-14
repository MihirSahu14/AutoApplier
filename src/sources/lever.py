"""Lever public job-board scraper.

Endpoint per company:
  https://api.lever.co/v0/postings/<slug>?mode=json
"""
from typing import Iterable
import httpx
from bs4 import BeautifulSoup

BASE = "https://api.lever.co/v0/postings/{slug}?mode=json"


def _clean_html(html: str) -> str:
    if not html:
        return ""
    return BeautifulSoup(html, "lxml").get_text("\n", strip=True)


def fetch_company(slug: str) -> list[dict]:
    r = httpx.get(BASE.format(slug=slug), timeout=30)
    if r.status_code != 200:
        return []
    data = r.json()
    if not isinstance(data, list):
        return []
    out = []
    for j in data:
        cats = j.get("categories", {}) or {}
        location = cats.get("location", "")
        desc = _clean_html(j.get("descriptionPlain") or j.get("description", ""))
        # add lists block
        if j.get("lists"):
            for lst in j["lists"]:
                desc += "\n\n" + (lst.get("text", "") or "")
                desc += "\n" + _clean_html(lst.get("content", "") or "")
        out.append({
            "source_id": f"{slug}:{j['id']}",
            "company": (j.get("categories", {}).get("team") or slug).replace("-", " ").title(),
            "title": j.get("text", ""),
            "location": location,
            "url": j.get("hostedUrl") or j.get("applyUrl"),
            "description": desc,
            "posted_at": str(j.get("createdAt", "")) if j.get("createdAt") else None,
        })
        # override company name with the slug since lever doesn't always include it
        out[-1]["company"] = slug.replace("-", " ").title()
    return out


def fetch(slugs: Iterable[str]) -> list[dict]:
    rows = []
    for s in slugs:
        try:
            rows.extend(fetch_company(s))
        except Exception as e:
            print(f"[lever] {s} failed: {e}")
    return rows
