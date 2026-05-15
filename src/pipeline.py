"""Shared business logic so CLI + Web UI use the same code paths."""
import json
import re
from pathlib import Path

from . import config as cfg_mod
from . import budget, db, docx_render, profile as profile_mod, tailor
from .paths import OUTPUT_DIR


def slug(s: str, n: int = 40) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "_", s or "").strip("_")
    return (s[:n] or "company").lower()


def output_dir_for(job_id: int, company: str) -> Path:
    return OUTPUT_DIR / f"{job_id}_{slug(company)}"


def package_paths(job_id: int, company: str, name: str) -> dict:
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
    cfg = cfg or cfg_mod.load()
    profile = profile_mod.load()

    job_row = db.get_job(job_id)
    if not job_row:
        raise ValueError(f"No job {job_id}")
    job = dict(job_row)

    t_cfg = cfg["providers"]["tailoring"]
    provider = t_cfg["provider"]
    model = t_cfg["model"]
    stage_caps = cfg["budget"]["stage_caps"]
    pricing = cfg.get("pricing", {})

    candidate = profile_mod.candidate_text(profile)
    if not candidate:
        raise ValueError(
            "No resume uploaded and no experience summary set. "
            "Open Settings to add one."
        )
    profile_block = profile_mod.build_profile_block(profile, candidate)

    base = tailor.parse_base_resume(
        candidate, provider=provider, model=model,
        stage_caps=stage_caps, pricing=pricing, force=regen_base,
    )
    tailored = tailor.tailor_resume(
        base, job, profile_block, provider=provider, model=model,
        stage_caps=stage_caps, pricing=pricing,
    )
    tailored["header"] = profile_mod.render_header_from_profile(profile)

    cover_text = None
    if not no_cover:
        cover_text = tailor.write_cover_letter(
            base, job, profile_block, provider=provider, model=model,
            stage_caps=stage_caps, pricing=pricing,
        )

    name = profile["contact"]["name"] or "candidate"
    paths = package_paths(job_id, job["company"], name)
    docx_render.render_resume(tailored, paths["resume_docx"])
    paths["resume_json"].write_text(json.dumps(tailored, indent=2), encoding="utf-8")
    if cover_text:
        docx_render.render_cover_letter(
            cover_text, tailored["header"], job["company"], paths["cover_docx"],
        )
        paths["cover_txt"].write_text(cover_text, encoding="utf-8")

    db.upsert_application(
        job_id=job_id, status="To apply",
        resume_path=str(paths["resume_docx"]),
        cover_letter_path=str(paths["cover_docx"]) if cover_text else None,
    )

    return {
        "job": job,
        "paths": paths,
        "cover_text": cover_text,
        "tailoring_spent_today": budget.stage_spent_usd("tailoring"),
    }
