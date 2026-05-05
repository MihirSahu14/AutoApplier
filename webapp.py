"""JSON API backend for the Auto Job Applier React UI.

Run: `python webapp.py`  -> http://localhost:8765 (API)
The React dev server (vite) runs on :5173 and proxies /api/* here.
"""
import json
import threading
import webbrowser
from pathlib import Path

from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from src import budget, db, pipeline, prefilter
from src import config as cfg_mod
from src import export as export_mod
from src import resume as resume_mod
from src.scorer import score_job, build_profile_block
from src.sources import hn

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
        job_id, j["company"], cfg_mod.load()["profile"]["name"]
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
        job_id, j["company"], cfg_mod.load()["profile"]["name"]
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


# ---- bulk actions ----

@app.post("/api/run/ingest")
def api_run_ingest():
    cfg = cfg_mod.load()
    months = cfg["sources"]["hn_who_is_hiring"]["months_back"]

    def _do():
        rows = hn.fetch(months_back=months)
        for r in rows:
            db.upsert_job(
                source="hn", source_id=r["source_id"],
                company=r["company"], title=r["title"],
                location=r["location"], url=r["url"],
                description=r["description"], posted_at=r["posted_at"],
            )

    started = _start("ingest", _do)
    return {"started": started}


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
    resume_text = resume_mod.extract_text(cfg["profile"]["resume_pdf"])
    profile = build_profile_block(cfg, resume_text)

    def _do():
        for j in db.unscored_jobs():
            try:
                result = score_job(profile, dict(j), model=model,
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
