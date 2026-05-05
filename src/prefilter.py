"""Free regex pre-filter that runs BEFORE Claude scoring.

Designed to be conservative: only disqualifies on clear, unambiguous signals.
Borderline cases pass through to the LLM scorer.
"""
import re

# Keywords that almost always mean "no F-1/OPT need apply"
SPONSOR_PATTERNS = [
    r"\bno\s+sponsorship\b",
    r"\bunable to sponsor\b",
    r"\bwill not sponsor\b",
    r"\bcannot sponsor\b",
    r"\bdo(?:es)? not sponsor\b",
    r"\bnot able to sponsor\b",
    r"\bsponsorship is not (?:available|offered)\b",
    r"\bno\s+(?:work\s+)?visa\b",
    r"\bno\s+h-?1b\b",
]

CITIZENSHIP_PATTERNS = [
    r"\bus\s+citizen(?:ship)?\s+(?:is\s+)?required\b",
    r"\bmust\s+be\s+(?:a\s+)?us\s+citizen\b",
    r"\bauthorized to work in the (?:us|united states) without sponsorship\b",
    r"\bus\s+citizens?\s+(?:and\s+)?(?:permanent\s+residents?|green\s+card)\s+only\b",
]

CLEARANCE_PATTERNS = [
    r"\bactive\s+(?:security\s+)?clearance\b",
    r"\bts[/-]sci\b",
    r"\btop\s+secret\b",
    r"\bsecret\s+clearance\b",
    r"\bpublic\s+trust\b",
]

# Title keywords that signal seniority well above new-grad — only DQ if ALSO
# accompanied by a years requirement, since "Senior Engineer" alone is sometimes
# used loosely at startups.
SENIOR_TITLE_PATTERNS = [
    r"\b(?:senior|sr\.?|staff|principal|lead|director|head\s+of|vp|vice\s+president)\b",
]
YEARS_REQUIRED_PATTERNS = [
    r"\b(?:5|6|7|8|9|10|11|12|15)\+?\s*(?:years?|yrs?)\b",
    r"\bminimum\s+(?:of\s+)?(?:5|6|7|8|9|10)\s*(?:years?|yrs?)\b",
]

# Roles that are clearly not engineering
NON_ENG_TITLE_PATTERNS = [
    r"\b(?:sales|account executive|business development|marketing|recruiter|"
    r"talent (?:acquisition|partner)|hr\b|human resources|chief of staff|"
    r"product manager|product designer|ux researcher|content writer|"
    r"customer support|customer success|finance|accounting|legal|"
    r"office manager|executive assistant)\b",
]
# Founding generalist roles override the non-eng filter
FOUNDING_PATTERNS = [r"\bfounding\b", r"\bfounder\b"]


def _matches_any(patterns: list[str], text: str) -> str | None:
    for p in patterns:
        m = re.search(p, text, re.IGNORECASE)
        if m:
            return m.group(0)
    return None


def check(job: dict) -> tuple[bool, str | None]:
    """Return (passed, reason). passed=False means disqualify; reason is the matched phrase."""
    text = " ".join(filter(None, [
        job.get("title", ""), job.get("description", ""), job.get("location", "")
    ]))
    title = (job.get("title") or "").lower()

    if hit := _matches_any(SPONSOR_PATTERNS, text):
        return False, f"No-sponsorship clause: '{hit}'"
    if hit := _matches_any(CITIZENSHIP_PATTERNS, text):
        return False, f"US citizenship required: '{hit}'"
    if hit := _matches_any(CLEARANCE_PATTERNS, text):
        return False, f"Security clearance required: '{hit}'"

    senior_hit = _matches_any(SENIOR_TITLE_PATTERNS, title)
    years_hit = _matches_any(YEARS_REQUIRED_PATTERNS, text)
    if senior_hit and years_hit:
        return False, f"Senior role with experience requirement: '{senior_hit}' + '{years_hit}'"

    if not _matches_any(FOUNDING_PATTERNS, title):
        if hit := _matches_any(NON_ENG_TITLE_PATTERNS, title):
            return False, f"Not an engineering role: '{hit}'"

    return True, None
