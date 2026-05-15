"""Resume tailoring + cover letter generation.

Uses whichever provider is configured for the 'tailoring' stage.
Free providers (groq/gemini/ollama) skip the dollar budget check.
"""
import json
from pathlib import Path

from . import budget, llm, profile as profile_mod
from .paths import CACHE_DIR

BASE_RESUME_JSON = CACHE_DIR / "resume_base.json"


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

Preserve the candidate's exact wording in every bullet. Output JSON only."""


TAILOR_SYSTEM = """You tailor a candidate's resume for a specific job.

Hard rules:
1. NEVER REMOVE anything. Every bullet, role, project, education entry, and
   skill category MUST appear in the output. No shortening, no trimming.
2. NEVER fabricate. Reword <=15% of a bullet's words to use JD vocabulary,
   but only when the underlying fact is already in the source bullet.
3. REORDER for relevance: most JD-relevant bullets first within each role;
   most relevant roles/projects first; matched skills first.
4. Header unchanged — copy verbatim.
5. Output the JSON object only, no prose, no markdown fences."""


COVER_SYSTEM = """You write a concise, personal cover letter for a job application.

Voice: first-person, warm, confident — like writing to a smart acquaintance.
Avoid: "passionate", "go-getter", "I am writing to apply", "would love the
opportunity", "synergy", "rockstar", "ninja".

Structure (3 short paragraphs, 240-310 words, plain text only — no markdown):
  1. Hook + why this company/role specifically. Reference something concrete
     from the JD (product, mission, technical problem, team size, recent news).
  2. The strongest 1-2 concrete experiences from the resume that map to the
     job. Be specific: project name, tech, what was built, metric/outcome.
  3. Short close: interest in talking, availability, sign with first name only.

STARTUP RULE — apply when company is a startup (<50 people, early-stage, YC,
"small team", seed/Series A): include ONE sincere sentence about wanting to
work in a startup environment (ownership, fast shipping, broad scope).

Hard rules:
- NEVER fabricate. Every fact from the resume JSON only.
- Output the letter only, no preamble."""


def _strip(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    return text


def _chat(provider: str, model: str, system: str, user: str, max_tokens: int,
          stage: str, stage_caps: dict, pricing: dict) -> str:
    api_key = profile_mod.provider_key(provider)
    if not llm.is_free(provider):
        budget.check(stage, stage_caps)
    text, usage = llm.chat(
        provider=provider, model=model, system=system, user=user,
        max_tokens=max_tokens, api_key=api_key,
    )
    if not llm.is_free(provider):
        budget.record(stage, model, usage.input_tokens, usage.output_tokens, pricing)
    return text


def parse_base_resume(resume_text: str, provider: str, model: str, stage_caps: dict,
                      pricing: dict, force: bool = False) -> dict:
    if BASE_RESUME_JSON.exists() and not force:
        return json.loads(BASE_RESUME_JSON.read_text(encoding="utf-8"))
    text = _chat(provider, model, PARSE_SYSTEM, resume_text, 4000,
                 "tailoring", stage_caps, pricing)
    data = json.loads(_strip(text))
    BASE_RESUME_JSON.parent.mkdir(parents=True, exist_ok=True)
    BASE_RESUME_JSON.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return data


def tailor_resume(base: dict, job: dict, profile_block: str,
                  provider: str, model: str, stage_caps: dict, pricing: dict) -> dict:
    job_block = (
        f"Company: {job['company']}\n"
        f"Title: {job['title']}\n"
        f"Location: {job.get('location') or 'unspecified'}\n\n"
        f"Description:\n{job['description'][:6000]}"
    )
    user = (
        f"## CANDIDATE PROFILE\n{profile_block}\n\n"
        f"## BASE RESUME (JSON)\n{json.dumps(base, indent=2)}\n\n"
        f"## JOB\n{job_block}\n\nReturn tailored resume JSON only."
    )
    text = _chat(provider, model, TAILOR_SYSTEM, user, 4000,
                 "tailoring", stage_caps, pricing)
    return json.loads(_strip(text))


def write_cover_letter(base: dict, job: dict, profile_block: str,
                       provider: str, model: str, stage_caps: dict, pricing: dict) -> str:
    job_block = (
        f"Company: {job['company']}\n"
        f"Title: {job['title']}\n"
        f"Location: {job.get('location') or 'unspecified'}\n\n"
        f"Description:\n{job['description'][:6000]}"
    )
    user = (
        f"## CANDIDATE PROFILE\n{profile_block}\n\n"
        f"## RESUME (source of truth — do not invent)\n"
        f"{json.dumps(base, indent=2)}\n\n"
        f"## JOB\n{job_block}\n\nWrite the cover letter."
    )
    return _chat(provider, model, COVER_SYSTEM, user, 900,
                 "tailoring", stage_caps, pricing)
