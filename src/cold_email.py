"""Cold email drafter. Uses whichever provider is configured for 'outreach'."""
import json

from . import budget, llm, profile as profile_mod


SYSTEM = """You write short cold outreach emails for a job seeker reaching out
to a specific person at a company about a specific role.

Rules:
- Output STRICT JSON: {"subject": str, "body": str}.  No prose around it.
- Subject: under 9 words.  Specific.  Not clickbait.
- Body: 90-140 words.  3 short paragraphs.  Plain text only.
  1. Why you're emailing THIS person about THIS role — specific.
  2. The strongest 1-2 concrete experiences from the resume that match the role.
     Be specific: project, tech, metric.
  3. A clear ask: 15-min chat / consideration for the role.
- Voice: confident, warm — like emailing a smart acquaintance.
- NEVER fabricate. Only facts from the resume.
- Avoid clichés: "passionate", "I came across", "would love the opportunity".
- Sign with the candidate's first name only (last line of body).
- Output JSON only."""


def _strip(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    return text


def draft_email(profile_block: str, candidate_text: str, job: dict, contact: dict,
                provider: str, model: str, stage_caps: dict, pricing: dict) -> dict:
    api_key = profile_mod.provider_key(provider)
    if not llm.is_free(provider):
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

    text, usage = llm.chat(
        provider=provider, model=model, system=SYSTEM, user=user,
        max_tokens=700, api_key=api_key,
    )
    if not llm.is_free(provider):
        budget.record("outreach", model, usage.input_tokens, usage.output_tokens, pricing)

    data = json.loads(_strip(text))
    return {"subject": data.get("subject", "").strip(),
            "body": data.get("body", "").strip()}
