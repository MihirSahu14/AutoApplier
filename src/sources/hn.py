"""Hacker News 'Who is hiring?' scraper.

Public Algolia/HN Firebase API — no auth, no anti-bot. Returns top-level
comments from the most recent monthly 'Who is hiring?' threads as job rows.
"""
import re
import httpx
from datetime import datetime, timezone
from bs4 import BeautifulSoup

ALGOLIA = "https://hn.algolia.com/api/v1"
FIREBASE = "https://hacker-news.firebaseio.com/v0"


def find_recent_threads(limit_months: int = 1) -> list[int]:
    """Find recent 'Ask HN: Who is hiring?' thread IDs."""
    r = httpx.get(
        f"{ALGOLIA}/search",
        params={
            "query": "Ask HN: Who is hiring?",
            "tags": "story,author_whoishiring",
            "hitsPerPage": limit_months,
        },
        timeout=30,
    )
    r.raise_for_status()
    return [int(h["objectID"]) for h in r.json()["hits"]]


def fetch_thread_comments(thread_id: int) -> list[dict]:
    r = httpx.get(
        f"{ALGOLIA}/search",
        params={"tags": f"comment,story_{thread_id}", "hitsPerPage": 1000},
        timeout=60,
    )
    r.raise_for_status()
    return r.json()["hits"]


def parse_comment(comment: dict) -> dict | None:
    html = comment.get("comment_text") or ""
    if not html:
        return None
    soup = BeautifulSoup(html, "lxml")
    text = soup.get_text("\n", strip=True)
    if len(text) < 80:
        return None

    first_line = text.split("\n", 1)[0]
    company = None
    m = re.match(r"^([A-Z][\w&.\-' ]{1,60}?)\s*[\|\(\-–—]", first_line)
    if m:
        company = m.group(1).strip()
    elif " | " in first_line:
        company = first_line.split(" | ")[0].strip()

    location = None
    loc_match = re.search(
        r"\b(REMOTE|Remote|San Francisco|New York|NYC|SF|Bay Area|US[A]?|"
        r"United States|California|Boston|Seattle|Austin|Chicago|London|Berlin|"
        r"Onsite|Hybrid)\b", first_line)
    if loc_match:
        location = loc_match.group(0)

    title = None
    title_match = re.search(
        r"\b(Software Engineer|SWE|Senior Engineer|Founding Engineer|"
        r"AI Engineer|ML Engineer|Backend|Frontend|Full[- ]?stack|Staff Engineer|"
        r"Principal Engineer|Data Engineer|Infrastructure Engineer|Platform Engineer)"
        r"[A-Za-z /+\-]*", text, re.IGNORECASE)
    if title_match:
        title = title_match.group(0).strip()

    posted = datetime.fromtimestamp(
        comment.get("created_at_i", 0), tz=timezone.utc).isoformat()

    return {
        "source_id": str(comment["objectID"]),
        "company": company or "(unknown)",
        "title": title or "(see description)",
        "location": location,
        "url": f"https://news.ycombinator.com/item?id={comment['objectID']}",
        "description": text,
        "posted_at": posted,
    }


def fetch(months_back: int = 1) -> list[dict]:
    out = []
    for tid in find_recent_threads(limit_months=months_back):
        for c in fetch_thread_comments(tid):
            row = parse_comment(c)
            if row:
                out.append(row)
    return out
