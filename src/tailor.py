"""Resume tailoring + cover letter generation using Sonnet 4.5.

Two-step flow:
  1. parse_base_resume(text) -> structured JSON (one-time, cached on disk).
  2. tailor_resume(base, job, profile) -> tailored JSON for a specific job.
  3. write_cover_letter(base, job, profile) -> plain-text cover letter.

Hard rule: the tailor NEVER fabricates. It only reorders, prunes, and lightly
rephrases bullets that already exist in the base resume.
"""
import json
import os
from pathlib import Path

from anthropic import Anthropic

from . import budget

ROOT = Path(__file__).resolve().parent.parent
BASE_RESUME_JSON = ROOT / "data" / "cache" / "resume_base.json"


PARSE_SYSTEM = """You extract a structured resume from raw text.

Return STRICT JSON, this exact schema (omit empty arrays, never invent fields):
{
  "header": {
    "name": str, "location": str, "phone": str, "email": str,
    "links": [{"label": str, "url": str}]
  },
  "education": [
    {"school": str, "degree": str, "location": str, "dates": str, "bullets": [str]}
  ],
  "experience": [
    {"company": str, "title": str, "location": str, "dates": str, "bullets": [str]}
  ],
  "projects": [
    {"name": str, "tech": str, "url": str, "date": str, "bullets": [str]}
  ],
  "skills": { "<Category>": [str] }
}

Preserve the candidate's exact wording in every bullet — do not paraphrase, do not
shorten, do not add.  Keep all bullets you find.  Output JSON only."""


TAILOR_SYSTEM = """You tailor a candidate's resume for a specific job.

INPUT: a JSON resume + a job posting + the candidate's targeting profile.
OUTPUT: the SAME JSON schema, tailored.

Rules — read carefully:
1. NEVER fabricate.  Every bullet in your output MUST be a faithful version of an
   existing input bullet (you may reword <=30% of the words to match the JD's
   vocabulary, but the underlying fact, technologies, and metrics must come
   from the source).
2. Reorder bullets within each role so the most JD-relevant ones come first.
3. Drop the weakest bullets to fit ONE page.  Target ~22-28 total bullets across
   experience+projects+education combined.  Keep at least 2 bullets per kept role.
4. Reorder experience entries by relevance to the role — but keep dates accurate.
5. Reorder skills: put categories and items that match the JD first.
6. Drop entire roles or projects only if clearly irrelevant AND the resume would
   otherwise overflow.
7. Header is unchanged — copy it through verbatim.
8. Output the JSON object only, no prose, no markdown fences."""


COVER_SYSTEM = """You write a concise, specific cover letter for a job application.

Constraints:
- 3 short paragraphs, 250-310 words total.
- Plain text only.  No markdown, no bullet points, no headings.
- Paragraph 1: 2-3 sentences on why THIS company/role specifically — reference
  something concrete from the JD (mission, product, tech, team).
- Paragraph 2: the strongest 1-2 experiences from the resume that map to the
  job's requirements.  Be specific (project name, tech, metric).
- Paragraph 3: short close — interest in talking, availability, signature.
- NEVER fabricate.  Only use facts present in the resume JSON.
- Avoid clichés: "passionate", "go-getter", "team player", "rockstar", "ninja",
  "I would love the opportunity", "I am writing to apply".
- Open with something other than "I am writing to apply for..."
- Sign off with the candidate's first name only.

Output the letter only, no preamble."""


def _client() -> Anthropic:
    return Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])


def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    return text


def parse_base_resume(resume_text: str, model: str, stage_caps: dict, pricing: dict,
                      force: bool = False) -> dict:
    """Parse raw resume text into structured JSON. Cached after first call."""
    if BASE_RESUME_JSON.exists() and not force:
        return json.loads(BASE_RESUME_JSON.read_text(encoding="utf-8"))

    budget.check("tailoring", stage_caps)
    msg = _client().messages.create(
        model=model,
        max_tokens=4000,
        system=PARSE_SYSTEM,
        messages=[{"role": "user", "content": resume_text}],
    )
    budget.record("tailoring", model, msg.usage.input_tokens,
                  msg.usage.output_tokens, pricing)

    data = json.loads(_strip_fences(msg.content[0].text))
    BASE_RESUME_JSON.parent.mkdir(parents=True, exist_ok=True)
    BASE_RESUME_JSON.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return data


def tailor_resume(base: dict, job: dict, profile_block: str, model: str,
                  stage_caps: dict, pricing: dict) -> dict:
    """Return a tailored copy of `base` for this job."""
    budget.check("tailoring", stage_caps)
    job_block = (
        f"Company: {job['company']}\n"
        f"Title: {job['title']}\n"
        f"Location: {job.get('location') or 'unspecified'}\n"
        f"URL: {job['url']}\n\n"
        f"Description:\n{job['description'][:6000]}"
    )
    user = (
        f"## CANDIDATE PROFILE\n{profile_block}\n\n"
        f"## BASE RESUME (JSON)\n{json.dumps(base, indent=2)}\n\n"
        f"## JOB\n{job_block}\n\n"
        f"Return the tailored resume JSON only."
    )
    msg = _client().messages.create(
        model=model,
        max_tokens=4000,
        system=TAILOR_SYSTEM,
        messages=[{"role": "user", "content": user}],
    )
    budget.record("tailoring", model, msg.usage.input_tokens,
                  msg.usage.output_tokens, pricing)
    return json.loads(_strip_fences(msg.content[0].text))


def write_cover_letter(base: dict, job: dict, profile_block: str, model: str,
                       stage_caps: dict, pricing: dict) -> str:
    """Return a plain-text cover letter for this job."""
    budget.check("tailoring", stage_caps)
    job_block = (
        f"Company: {job['company']}\n"
        f"Title: {job['title']}\n"
        f"Location: {job.get('location') or 'unspecified'}\n\n"
        f"Description:\n{job['description'][:6000]}"
    )
    user = (
        f"## CANDIDATE PROFILE\n{profile_block}\n\n"
        f"## RESUME (JSON, source of truth — do not invent anything)\n"
        f"{json.dumps(base, indent=2)}\n\n"
        f"## JOB\n{job_block}\n\n"
        f"Write the cover letter."
    )
    msg = _client().messages.create(
        model=model,
        max_tokens=900,
        system=COVER_SYSTEM,
        messages=[{"role": "user", "content": user}],
    )
    budget.record("tailoring", model, msg.usage.input_tokens,
                  msg.usage.output_tokens, pricing)
    return msg.content[0].text.strip()
