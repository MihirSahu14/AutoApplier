"""Resume tailoring + cover letter generation using Sonnet 4.5.

Two-step flow:
  1. parse_base_resume(text) -> structured JSON (one-time, cached on disk).
  2. tailor_resume(base, job, profile) -> tailored JSON for a specific job.
  3. write_cover_letter(base, job, profile) -> plain-text cover letter.

Hard rule: the tailor NEVER fabricates. It only reorders, prunes, and lightly
rephrases bullets that already exist in the base resume.
"""
import json
from pathlib import Path

from anthropic import Anthropic

from . import budget, profile as profile_mod

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

Hard rules — read carefully:
1. NEVER REMOVE anything.  Every bullet, every role, every project, every
   education entry, and every skills category from the input MUST appear in
   the output.  No shortening, no trimming, no consolidation.
2. NEVER fabricate.  Every bullet must be a faithful version of an existing
   input bullet.  You MAY reword up to ~15% of the words in a bullet to use
   the job's vocabulary, but ONLY when the underlying fact, technology, and
   metric are already in the source bullet.  If you can't justify a rewrite
   from the source, leave the bullet exactly as-is.
3. REORDER for relevance:
   - Bullets within each role: most JD-relevant first.
   - Experience entries: most JD-relevant role first (dates/text unchanged).
   - Project entries: most JD-relevant project first.
   - Skills: put matched categories first; within each category, put matched
     items first.
4. Header is unchanged — copy it through verbatim.
5. Output the JSON object only.  No prose, no markdown fences, no commentary."""


COVER_SYSTEM = """You write a concise, personal cover letter for a job application.

Voice & tone:
- First-person, conversational, warm — like writing to a smart friend who works
  at the company.  Confident, not stiff.  Specific, not generic.
- Avoid corporate-speak and clichés: no "passionate", "go-getter", "team
  player", "rockstar", "ninja", "I am writing to apply for", "I would love the
  opportunity to", "synergy", "leverage" (as a verb).
- Don't open with "I am writing to apply..." — open with something the reader
  will actually want to keep reading.

Structure (3 short paragraphs, 240-310 words total, plain text only — no
markdown, no bullet points, no headings):

  1. Hook + why this company/role specifically.  Reference something concrete
     from the JD (the product, the mission, the technical problem, the team
     size, recent news, a value).  This must read as if the candidate
     actually read the posting.

  2. The strongest 1-2 concrete experiences from the resume that map to what
     the job needs.  Be specific: project or company name, the tech, what was
     built, and a metric or outcome when one is in the resume.  Connect them
     back to what the role requires.

  3. Short close: interest in talking, availability if it's in the profile,
     sign off with the candidate's FIRST NAME only.

STARTUP RULE — apply when the company is a startup (signals: <50 people,
"early-stage", "Series A/B/seed", "founding", "small team", YC company, fast
shipping, broad role scope, mention of 'wear many hats'):
- Include ONE sincere sentence in paragraph 1 OR 2 about wanting to work in a
  startup environment — what specifically draws the candidate to it (e.g.
  ownership over what ships, fast iteration, working close to users, broad
  scope across the stack).  Make it feel earned, not pasted in.

Hard rules:
- NEVER fabricate.  Every fact must come from the resume JSON.
- NEVER mention things the candidate hasn't done.
- Don't repeat the resume — interpret it and connect it to the role.

Output the letter only, no preamble."""


def _client() -> Anthropic:
    return Anthropic(api_key=profile_mod.anthropic_key())


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
