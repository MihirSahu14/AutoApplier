"""JSON API backend for the Auto Job Applier React UI.

Run: `python webapp.py`  -> http://localhost:8765 (API)
The React dev server (vite) runs on :5173 and proxies /api/* here.
"""
import json
import threading
import webbrowser
from pathlib import Path

from fastapi import FastAPI, BackgroundTasks, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from src import autofill, budget, cold_email, contacts as contacts_mod, db, pipeline, prefilter, profile as profile_mod
from src import config as cfg_mod
from src import export as export_mod
from src.scorer import score_job
from src.sources import hn, greenhouse, lever, ashby

ROOT = Path(__file__).resolve().parent

# Track which background jobs are running so the UI can show a spinner.
_running: set[str] = set()
_running_lock = threading.Lock()

STATUSES = [
    "Not started", "To apply", "Applied", "Phone screen", "Technical",
    "Onsite", "Offer", "Rejected", "Withdrawn", "Ghosted",
]

app = FastAPI(title="Auto Job Applier API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # vite dev server
    allow_methods=["*"],
    allow_headers=["*"],
)


# ------------- helpers -------------

def _stage_table() -> dict:
    cfg = cfg_mod.load()
    caps = cfg["budget"]["stage_caps"]
    return {
        "stages": [
            {
                "name": s, "cap": caps[s],
                "spent": round(budget.stage_spent_usd(s), 4),
                "remaining": round(budget.stage_remaining_usd(s, caps), 4),
                "pct": min(100, int(100 * budget.stage_spent_usd(s) / caps[s])) if caps[s] else 0,
            }
            for s in caps
        ],
        "daily": cfg["budget"]["daily_usd"],
        "total_today": round(budget.today_spent_usd(), 4),
        "running": sorted(_running),
    }


def _start(name: str, fn):
    """Run `fn` once in a background thread; track 'running' state."""
    with _running_lock:
        if name in _running:
            return False
        _running.add(name)

    def _wrap():
        try:
            fn()
        finally:
            with _running_lock:
                _running.discard(name)

    threading.Thread(target=_wrap, daemon=True).start()
    return True


def _job_or_404(job_id: int):
    j = db.get_job(job_id)
    if not j:
        raise HTTPException(404, f"Job {job_id} not found")
    return j


# ------------- API -------------

@app.get("/api/setup-status")
def api_setup_status():
    p = profile_mod.load()
    has_resume = bool(p.get("resume_pdf") and Path(p["resume_pdf"]).exists())
    return {
        "configured": profile_mod.is_configured(),
        "has_name": bool(p["contact"]["name"]),
        "has_email": bool(p["contact"]["email"]),
        "has_resume": has_resume,
        "has_experience_summary": bool(p.get("experience_summary")),
        "has_anthropic_key": bool(profile_mod.anthropic_key()),
        "db_initialized": db.DB_PATH.exists(),
    }


@app.get("/api/profile")
def api_get_profile():
    p = profile_mod.load()
    # Mask API keys for transport — UI shows "set/unset"
    masked = json.loads(json.dumps(p))
    masked["api_keys"] = {
        k: ("•" * 8 + (v[-4:] if v else "")) if v else ""
        for k, v in p["api_keys"].items()
    }
    masked["resume_pdf_filename"] = (
        Path(p["resume_pdf"]).name if p.get("resume_pdf") else ""
    )
    return masked


@app.put("/api/profile")
def api_update_profile(body: dict):
    """Partial update. `api_keys.*` values that are blank or all-bullets are ignored."""
    current = profile_mod.load()
    # Deep merge dicts; replace scalars/lists.
    def _merge(dst, src):
        for k, v in src.items():
            if isinstance(v, dict) and isinstance(dst.get(k), dict):
                _merge(dst[k], v)
            else:
                dst[k] = v
    incoming = body or {}
    if "api_keys" in incoming:
        cleaned = {}
        for k, v in incoming["api_keys"].items():
            if not v or set(v) <= {"•"}:
                continue  # keep existing
            cleaned[k] = v
        incoming["api_keys"] = cleaned
    _merge(current, incoming)
    profile_mod.save(current)
    db.init_db()  # ensure DB exists once profile is saved
    return {"ok": True}


@app.post("/api/profile/upload-resume")
def api_upload_resume(file: UploadFile = File(...)):
    if not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(400, "Only PDF resumes are supported.")
    dest_dir = ROOT / "data" / "resume"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / file.filename
    with open(dest, "wb") as f:
        f.write(file.file.read())
    # Bust the parsed-resume cache since the base resume changed
    cache = ROOT / "data" / "cache" / "resume.txt"
    base_json = ROOT / "data" / "cache" / "resume_base.json"
    for f in (cache, base_json):
        if f.exists():
            f.unlink()

    p = profile_mod.load()
    p["resume_pdf"] = str(dest)
    profile_mod.save(p)
    return {"ok": True, "filename": dest.name, "path": str(dest)}


@app.get("/api/budget")
def api_budget():
    return _stage_table()


@app.get("/api/meta")
def api_meta():
    with db.connect() as c:
        sources = [r[0] for r in c.execute(
            "SELECT DISTINCT source FROM jobs ORDER BY source").fetchall()]
        counts = {
            "total":  c.execute("SELECT COUNT(*) FROM jobs").fetchone()[0],
            "scored": c.execute("SELECT COUNT(*) FROM scores").fetchone()[0],
            "qualified": c.execute(
                "SELECT COUNT(*) FROM scores WHERE disqualified = 0"
            ).fetchone()[0],
            "applied": c.execute(
                "SELECT COUNT(*) FROM applications WHERE status NOT IN ('Not started','To apply')"
            ).fetchone()[0],
        }
    return {"sources": sources, "statuses": STATUSES, "counts": counts}


@app.get("/api/jobs")
def api_jobs(min_score: int = 0, status: str = "", source: str = "",
             q: str = "", include_dq: bool = False, limit: int = 200):
    sql = (
        "SELECT j.id, j.source, j.company, j.title, j.location, j.url, "
        "j.posted_at, "
        "s.score, s.fit_summary, s.disqualified, s.disqualify_reason, "
        "a.status AS app_status, a.resume_path, a.cover_letter_path, a.notes "
        "FROM jobs j "
        "LEFT JOIN scores s ON s.job_id = j.id "
        "LEFT JOIN applications a ON a.job_id = j.id "
        "WHERE 1=1 "
    )
    params: list = []
    if min_score:
        sql += "AND COALESCE(s.score, 0) >= ? "
        params.append(min_score)
    if not include_dq:
        sql += "AND COALESCE(s.disqualified, 0) = 0 "
    if status:
        sql += "AND COALESCE(a.status,'Not started') = ? "
        params.append(status)
    if source:
        sql += "AND j.source = ? "
        params.append(source)
    if q:
        sql += "AND (LOWER(j.company) LIKE ? OR LOWER(j.title) LIKE ? OR LOWER(j.description) LIKE ?) "
        like = f"%{q.lower()}%"
        params += [like, like, like]
    sql += "ORDER BY COALESCE(s.score, -1) DESC, j.id DESC LIMIT ?"
    params.append(limit)
    with db.connect() as c:
        rows = c.execute(sql, params).fetchall()
    return {"jobs": [dict(r) for r in rows]}


@app.get("/api/jobs/{job_id}")
def api_job(job_id: int):
    j = dict(_job_or_404(job_id))
    paths = pipeline.package_paths(
        job_id, j["company"], profile_mod.load()["contact"]["name"] or "candidate"
    )
    cover_text = paths["cover_txt"].read_text(encoding="utf-8") if paths["cover_txt"].exists() else None
    j["have_resume"] = paths["resume_docx"].exists()
    j["have_cover"] = paths["cover_docx"].exists()
    j["cover_text"] = cover_text
    return j


class StatusUpdate(BaseModel):
    status: str
    notes: str | None = None


@app.put("/api/jobs/{job_id}/status")
def api_set_status(job_id: int, body: StatusUpdate):
    _job_or_404(job_id)
    db.upsert_application(job_id=job_id, status=body.status, notes=body.notes)
    return {"ok": True}


@app.post("/api/jobs/{job_id}/tailor")
def api_tailor(job_id: int, no_cover: bool = False):
    try:
        result = pipeline.generate_package(job_id, no_cover=no_cover)
    except budget.BudgetExceeded as e:
        raise HTTPException(429, str(e))
    return {
        "ok": True,
        "tailoring_spent_today": result["tailoring_spent_today"],
    }


@app.get("/api/jobs/{job_id}/download/{kind}")
def api_download(job_id: int, kind: str):
    j = dict(_job_or_404(job_id))
    paths = pipeline.package_paths(
        job_id, j["company"], profile_mod.load()["contact"]["name"] or "candidate"
    )
    f = {"resume": paths["resume_docx"], "cover": paths["cover_docx"]}.get(kind)
    if not f or not f.exists():
        raise HTTPException(404, "File not generated yet")
    return FileResponse(f, filename=f.name)


@app.post("/api/jobs/{job_id}/open")
def api_open(job_id: int):
    j = dict(_job_or_404(job_id))
    if j["url"]:
        webbrowser.open(j["url"])
    return {"ok": True}


class AutofillBody(BaseModel):
    url: str | None = None  # override URL (job.url often isn't the apply form)


@app.get("/api/jobs/{job_id}/contacts")
def api_list_contacts(job_id: int):
    _job_or_404(job_id)
    rows = db.list_contacts(job_id)
    return {"contacts": [dict(r) for r in rows]}


@app.post("/api/jobs/{job_id}/find-contacts")
def api_find_contacts(job_id: int):
    j = dict(_job_or_404(job_id))
    if not profile_mod.api_key("hunter"):
        raise HTTPException(412, "Hunter.io API key not set. Add it in Settings.")
    rows = contacts_mod.find_contacts_for_job(j)
    if not rows:
        return {"found": 0, "domain": contacts_mod.guess_domain(j["company"], j["description"] or "")}
    n = db.add_contacts(job_id, j["company"], rows)
    return {"found": n, "total_returned": len(rows),
            "domain": contacts_mod.guess_domain(j["company"], j["description"] or "")}


@app.post("/api/contacts/{contact_id}/draft-email")
def api_draft_email(contact_id: int):
    c = db.get_contact(contact_id)
    if not c:
        raise HTTPException(404, "Contact not found")
    contact = dict(c)
    job = db.get_job(contact["job_id"])
    if not job:
        raise HTTPException(404, "Job for contact not found")
    profile = profile_mod.load()
    if not profile_mod.is_configured():
        raise HTTPException(412, "Complete profile setup first.")
    cfg = cfg_mod.load()
    candidate = profile_mod.candidate_text(profile)
    profile_block = profile_mod.build_profile_block(profile, candidate)
    try:
        draft = cold_email.draft_email(
            profile_block, candidate, dict(job), contact,
            model=cfg["generation"]["model"],
            stage_caps=cfg["budget"]["stage_caps"],
            pricing=cfg["pricing"],
        )
    except budget.BudgetExceeded as e:
        raise HTTPException(429, str(e))
    db.save_email_draft(contact_id, draft["subject"], draft["body"])
    return draft


@app.post("/api/contacts/{contact_id}/mark-sent")
def api_mark_sent(contact_id: int):
    if not db.get_contact(contact_id):
        raise HTTPException(404, "Contact not found")
    db.mark_email_sent(contact_id)
    return {"ok": True}


@app.post("/api/jobs/{job_id}/autofill")
def api_autofill(job_id: int, body: AutofillBody):
    j = dict(_job_or_404(job_id))
    target_url = (body.url or "").strip() or j["url"]
    if not target_url:
        raise HTTPException(400, "No URL to open.")

    profile = profile_mod.load()
    if not profile_mod.is_configured():
        raise HTTPException(412, "Complete profile setup first.")

    paths = pipeline.package_paths(
        job_id, j["company"], profile["contact"]["name"] or "candidate"
    )
    if not paths["resume_docx"].exists():
        raise HTTPException(409, "Generate the tailored package first (resume/cover not found).")

    autofill.launch_autofill_thread(
        target_url, profile,
        paths["resume_docx"],
        paths["cover_docx"] if paths["cover_docx"].exists() else None,
    )
    # Save the apply URL on the application row so it persists
    db.upsert_application(job_id=job_id, status=j.get("app_status") or "To apply",
                          notes=j.get("notes"))
    return {"ok": True}


# ---- bulk actions ----

def _load_companies() -> dict:
    import yaml
    path = ROOT / "data" / "companies.yaml"
    if not path.exists():
        return {"greenhouse": [], "lever": [], "ashby": []}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _ingest_one(source: str, rows: list[dict]):
    for r in rows:
        db.upsert_job(
            source=source, source_id=r["source_id"],
            company=r["company"], title=r["title"],
            location=r["location"], url=r["url"],
            description=r["description"], posted_at=r["posted_at"],
        )


@app.post("/api/run/ingest")
def api_run_ingest(source: str = "all"):
    cfg = cfg_mod.load()
    months = cfg["sources"]["hn_who_is_hiring"]["months_back"]
    companies = _load_companies()

    def _do():
        if source in ("all", "hn"):
            try: _ingest_one("hn", hn.fetch(months_back=months))
            except Exception as e: print(f"[ingest:hn] {e}")
        if source in ("all", "greenhouse"):
            try: _ingest_one("greenhouse", greenhouse.fetch(companies.get("greenhouse", [])))
            except Exception as e: print(f"[ingest:gh] {e}")
        if source in ("all", "lever"):
            try: _ingest_one("lever", lever.fetch(companies.get("lever", [])))
            except Exception as e: print(f"[ingest:lever] {e}")
        if source in ("all", "ashby"):
            try: _ingest_one("ashby", ashby.fetch(companies.get("ashby", [])))
            except Exception as e: print(f"[ingest:ashby] {e}")

    return {"started": _start(f"ingest:{source}", _do)}


@app.get("/api/companies")
def api_get_companies():
    return _load_companies()


@app.put("/api/companies")
def api_set_companies(body: dict):
    import yaml
    path = ROOT / "data" / "companies.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    # whitelist keys
    out = {k: [str(s).strip() for s in (body.get(k) or []) if str(s).strip()]
           for k in ("greenhouse", "lever", "ashby")}
    path.write_text(yaml.safe_dump(out, sort_keys=False), encoding="utf-8")
    return {"ok": True, **out}


@app.post("/api/run/prefilter")
def api_run_prefilter():
    def _do():
        for j in db.unscored_jobs():
            passed, reason = prefilter.check(dict(j))
            if not passed:
                db.save_score(
                    job_id=j["id"], score=0,
                    fit_summary=f"[prefilter] {reason}",
                    disqualified=True, disqualify_reason=reason,
                    matched_skills=json.dumps([]),
                    missing_skills=json.dumps([]),
                )

    return {"started": _start("prefilter", _do)}


@app.post("/api/run/score")
def api_run_score():
    cfg = cfg_mod.load()
    stage_caps = cfg["budget"]["stage_caps"]
    pricing = cfg["pricing"]
    model = cfg["scoring"]["model"]
    profile_block = profile_mod.build_profile_block()

    def _do():
        for j in db.unscored_jobs():
            try:
                result = score_job(profile_block, dict(j), model=model,
                                   stage_caps=stage_caps, pricing=pricing)
            except budget.BudgetExceeded:
                break
            except Exception:
                continue
            db.save_score(
                job_id=j["id"],
                score=int(result.get("score", 0)),
                fit_summary=result.get("fit_summary", ""),
                disqualified=bool(result.get("disqualified", False)),
                disqualify_reason=result.get("disqualify_reason"),
                matched_skills=json.dumps(result.get("matched_skills", [])),
                missing_skills=json.dumps(result.get("missing_skills", [])),
            )

    return {"started": _start("score", _do)}


@app.post("/api/run/export")
def api_run_export():
    path = export_mod.export()
    return {"path": str(path)}


# ---- serve built React app in production (after `npm run build`) ----
_DIST = ROOT / "frontend" / "dist"
if _DIST.exists():
    app.mount("/", StaticFiles(directory=str(_DIST), html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("webapp:app", host="127.0.0.1", port=8765, reload=False)
