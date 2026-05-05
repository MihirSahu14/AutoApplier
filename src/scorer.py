"""Score jobs against the user's resume + targets using Claude (cheap model)."""
import json
import os
from anthropic import Anthropic

from . import budget

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
              pricing: dict) -> dict:
    budget.check("scoring", stage_caps)
    client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    job_block = (
        f"Company: {job['company']}\n"
        f"Title: {job['title']}\n"
        f"Location: {job.get('location') or 'unspecified'}\n"
        f"URL: {job['url']}\n\n"
        f"Description:\n{job['description'][:6000]}"
    )
    msg = client.messages.create(
        model=model,
        max_tokens=800,
        system=SYSTEM,
        messages=[{
            "role": "user",
            "content": f"## CANDIDATE\n{profile_block}\n\n## JOB\n{job_block}\n\nReturn JSON only.",
        }],
    )
    budget.record(
        stage="scoring",
        model=model,
        input_tokens=msg.usage.input_tokens,
        output_tokens=msg.usage.output_tokens,
        pricing=pricing,
    )
    text = msg.content[0].text.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    return json.loads(text)


def build_profile_block(cfg: dict, resume_text: str) -> str:
    t = cfg["targets"]
    v = cfg["visa"]
    return (
        f"Name: {cfg['profile']['name']}\n"
        f"Visa: {v['status']}; needs H-1B sponsorship eventually.\n"
        f"Target roles: {', '.join(t['roles'])}\n"
        f"Company size preference: {t['company_size']['min']}-{t['company_size']['max']} employees (startups)\n"
        f"Locations OK: {', '.join(t['locations_ok'])}; preferred: {', '.join(t['locations_preferred'])}\n"
        f"Salary floor: ${t['salary_min_usd']:,}\n"
        f"Disqualifiers (any of): {', '.join(cfg['visa']['disqualify_if'])}\n\n"
        f"Resume text:\n{resume_text}"
    )
