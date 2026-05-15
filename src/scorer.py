"""Score jobs against the user's resume + targets.

Uses whichever provider is configured for the 'scoring' stage.
Free providers (groq/gemini/ollama) skip the dollar budget check.
"""
import json

from . import budget, llm, profile as profile_mod

SYSTEM = """You are a job-fit scorer for a candidate applying to software roles.

You will receive (1) a candidate profile + resume text + targets, and (2) a job posting.
Output STRICT JSON with these keys:

{
  "score": int 0-100,             // overall fit
  "fit_summary": str,             // 1-2 sentences, plain English
  "disqualified": bool,           // true if a hard filter fires
  "disqualify_reason": str|null,  // which filter fired, if any
  "matched_skills": [str],        // resume skills that match the job
  "missing_skills": [str]         // job-required skills the resume lacks
}

Disqualify (hard filters) if ANY of these appear in the job:
- US citizenship required / clearance required
- "No sponsorship" / "will not sponsor" / "cannot sponsor"
- Senior/Staff/Principal-only role with 5+ years required (candidate is new-grad)
- Salary explicitly below the candidate's floor
- Role is not engineering (sales, marketing, ops, etc.) UNLESS it's "Founding" generalist

Score guidance:
- 90-100: ideal — startup, role match, tech stack overlap, US/preferred location
- 70-89: strong fit, apply
- 50-69: weak fit, only if low effort
- <50: skip

Only return the JSON object, no prose."""


def score_job(profile_block: str, job: dict, model: str, stage_caps: dict,
              pricing: dict, provider: str = "anthropic") -> dict:
    """Score one job. Skips dollar-budget enforcement for free providers."""
    api_key = profile_mod.provider_key(provider)

    if not llm.is_free(provider):
        budget.check("scoring", stage_caps)

    job_block = (
        f"Company: {job['company']}\n"
        f"Title: {job['title']}\n"
        f"Location: {job.get('location') or 'unspecified'}\n"
        f"URL: {job['url']}\n\n"
        f"Description:\n{job['description'][:6000]}"
    )
    user = f"## CANDIDATE\n{profile_block}\n\n## JOB\n{job_block}\n\nReturn JSON only."

    text, usage = llm.chat(
        provider=provider, model=model, system=SYSTEM, user=user,
        max_tokens=800, api_key=api_key,
    )

    if not llm.is_free(provider):
        budget.record("scoring", model, usage.input_tokens, usage.output_tokens, pricing)

    if text.startswith("```"):
        text = text.split("```", 2)[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    return json.loads(text)


def build_profile_block(profile: dict = None, candidate_text: str = None) -> str:
    return profile_mod.build_profile_block(profile, candidate_text)
