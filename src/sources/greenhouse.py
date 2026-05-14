"""Greenhouse public job-board scraper.

Endpoint per company:
  https://boards-api.greenhouse.io/v1/boards/<slug>/jobs?content=true
"""
import re
from typing import Iterable
import httpx
from bs4 import BeautifulSoup

BASE = "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true"


def _clean_html(html: str) -> str:
    if not html:
        return ""
    return BeautifulSoup(html, "lxml").get_text("\n", strip=True)


def _company_name(job: dict, fallback: str) -> str:
    return (job.get("company_name") or fallback or "").strip() or fallback


def fetch_company(slug: str) -> list[dict]:
    r = httpx.get(BASE.format(slug=slug), timeout=30)
    if r.status_code != 200:
        return []
    jobs = r.json().get("jobs", []) or []
    out = []
    for j in jobs:
        location = ""
        if isinstance(j.get("location"), dict):
            location = j["location"].get("name", "") or ""
        desc = _clean_html(j.get("content", "")) or ""
        out.append({
            "source_id": f"{slug}:{j['id']}",
            "company": _company_name(j, slug.replace("-", " ").title()),
            "title": j.get("title", ""),
            "location": location,
            "url": j.get("absolute_url"),
            "description": desc,
            "posted_at": j.get("updated_at") or j.get("created_at"),
        })
    return out


def fetch(slugs: Iterable[str]) -> list[dict]:
    rows = []
    for s in slugs:
        try:
            rows.extend(fetch_company(s))
        except Exception as e:
            print(f"[greenhouse] {s} failed: {e}")
    return rows
