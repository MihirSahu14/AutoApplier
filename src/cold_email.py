"""Cold email drafter: writes a short, personal email to a specific recipient
about a specific job, grounded in the candidate's resume.
"""
import json
from anthropic import Anthropic

from . import budget, profile as profile_mod


SYSTEM = """You write short cold outreach emails for a job seeker reaching out
to a specific person at a company about a specific role.

Rules:
- Output STRICT JSON: {"subject": str, "body": str}.  No prose around it.
- Subject: under 9 words.  Specific.  No "Re:" prefix.  Not clickbait.
- Body: 90-140 words.  3 short paragraphs.  Plain text only.
  1. Why you (the candidate) are emailing THIS person specifically — reference
     their role/company and the open job.
  2. The single strongest concrete experience or project from the candidate's
     resume that maps to the role.  Be specific (tech, metric, outcome).
  3. A clear one-sentence ask: 15-min chat / consideration for the role.
- Voice: confident, warm, conversational — like emailing a smart acquaintance.
- NEVER fabricate.  Every fact must come from the resume / profile.
- Avoid: "I hope this finds you well", "passionate", "I came across", "rockstar",
  "ninja", "synergy", excessive flattery.
- Sign with the candidate's first name only (the body should END with the name
  on its own line; no "Best regards,").
- Mention attached resume only if the prior turn says it will be attached."""


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


def draft_email(profile_block: str, candidate_text: str, job: dict, contact: dict,
                model: str, stage_caps: dict, pricing: dict) -> dict:
    """Generate {'subject', 'body'} for a single contact + job."""
    budget.check("outreach", stage_caps)

    contact_block = (
        f"Name: {contact.get('name') or '(unknown)'}\n"
        f"Title: {contact.get('title') or '(unknown)'}\n"
        f"Email: {contact.get('email')}\n"
        f"Company: {contact.get('company') or job.get('company')}"
    )
    job_block = (
        f"Company: {job['company']}\n"
        f"Title: {job.get('title') or '(see description)'}\n"
        f"Location: {job.get('location') or 'unspecified'}\n\n"
        f"Description:\n{(job.get('description') or '')[:4000]}"
    )

    user = (
        f"## CANDIDATE PROFILE\n{profile_block}\n\n"
        f"## CANDIDATE BACKGROUND (source of truth)\n{candidate_text}\n\n"
        f"## RECIPIENT\n{contact_block}\n\n"
        f"## JOB\n{job_block}\n\n"
        f"Return JSON {{\"subject\": ..., \"body\": ...}} only."
    )
    msg = _client().messages.create(
        model=model,
        max_tokens=700,
        system=SYSTEM,
        messages=[{"role": "user", "content": user}],
    )
    budget.record("outreach", model, msg.usage.input_tokens,
                  msg.usage.output_tokens, pricing)
    data = json.loads(_strip_fences(msg.content[0].text))
    return {"subject": data.get("subject", "").strip(),
            "body": data.get("body", "").strip()}
