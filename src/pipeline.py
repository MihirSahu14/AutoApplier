"""Shared business logic so CLI + Web UI use the same code paths."""
import json
import re
from pathlib import Path

from . import config as cfg_mod
from . import budget, db, docx_render, resume, tailor
from .scorer import build_profile_block

ROOT = Path(__file__).resolve().parent.parent


def slug(s: str, n: int = 40) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "_", s or "").strip("_")
    return (s[:n] or "company").lower()


def output_dir_for(job_id: int, company: str) -> Path:
    return ROOT / "data" / "output" / f"{job_id}_{slug(company)}"


def package_paths(job_id: int, company: str, name: str) -> dict:
    """Compute the canonical output paths for a job's package."""
    out = output_dir_for(job_id, company)
    name_slug = slug(name)
    return {
        "dir": out,
        "resume_docx": out / f"Resume_{name_slug}.docx",
        "cover_docx": out / f"CoverLetter_{name_slug}_{slug(company)}.docx",
        "resume_json": out / "tailored_resume.json",
        "cover_txt": out / "cover_letter.txt",
    }


def generate_package(job_id: int, *, cfg: dict | None = None, no_cover: bool = False,
                     regen_base: bool = False) -> dict:
    """Tailored resume + cover letter for one job. Returns paths and spend.

    Raises BudgetExceeded if any stage hits its cap.
    """
    cfg = cfg or cfg_mod.load()
    job_row = db.get_job(job_id)
    if not job_row:
        raise ValueError(f"No job {job_id}")
    job = dict(job_row)

    model = cfg["generation"]["model"]
    stage_caps = cfg["budget"]["stage_caps"]
    pricing = cfg["pricing"]

    resume_text = resume.extract_text(cfg["profile"]["resume_pdf"])
    profile = build_profile_block(cfg, resume_text)

    base = tailor.parse_base_resume(
        resume_text, model=model, stage_caps=stage_caps, pricing=pricing,
        force=regen_base,
    )
    tailored = tailor.tailor_resume(
        base, job, profile, model=model, stage_caps=stage_caps, pricing=pricing,
    )

    # Override Claude-generated header with authoritative profile from config
    p = cfg["profile"]
    tailored["header"] = {
        "name": p["name"],
        "location": p["location"],
        "phone": p["phone"],
        "email": p["email"],
        "links": [
            {"label": "LinkedIn", "url": p["linkedin"]},
            {"label": "GitHub",   "url": p["github"]},
            {"label": "Portfolio","url": p["portfolio"]},
        ],
    }

    cover_text = None
    if not no_cover:
        cover_text = tailor.write_cover_letter(
            base, job, profile, model=model, stage_caps=stage_caps, pricing=pricing,
        )

    paths = package_paths(job_id, job["company"], cfg["profile"]["name"])
    docx_render.render_resume(tailored, paths["resume_docx"])
    paths["resume_json"].write_text(json.dumps(tailored, indent=2), encoding="utf-8")
    if cover_text:
        docx_render.render_cover_letter(
            cover_text, tailored["header"], job["company"], paths["cover_docx"],
        )
        paths["cover_txt"].write_text(cover_text, encoding="utf-8")

    db.upsert_application(
        job_id=job_id,
        status="To apply",
        resume_path=str(paths["resume_docx"]),
        cover_letter_path=str(paths["cover_docx"]) if cover_text else None,
    )

    return {
        "job": job,
        "paths": paths,
        "cover_text": cover_text,
        "tailoring_spent_today": budget.stage_spent_usd("tailoring"),
    }
