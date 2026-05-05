import sqlite3
from pathlib import Path
from contextlib import contextmanager

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "jobs.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    source_id TEXT NOT NULL,
    company TEXT,
    title TEXT,
    location TEXT,
    url TEXT,
    description TEXT,
    raw_json TEXT,
    posted_at TEXT,
    ingested_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(source, source_id)
);

CREATE TABLE IF NOT EXISTS scores (
    job_id INTEGER PRIMARY KEY REFERENCES jobs(id) ON DELETE CASCADE,
    score INTEGER,
    fit_summary TEXT,
    disqualified INTEGER DEFAULT 0,
    disqualify_reason TEXT,
    matched_skills TEXT,
    missing_skills TEXT,
    scored_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS applications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    status TEXT NOT NULL,
    resume_path TEXT,
    cover_letter_path TEXT,
    notes TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_scores_score ON scores(score DESC);
CREATE INDEX IF NOT EXISTS idx_jobs_source ON jobs(source);
"""


def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with connect() as c:
        c.executescript(SCHEMA)


@contextmanager
def connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def upsert_job(source: str, source_id: str, **fields) -> int:
    cols = ["source", "source_id"] + list(fields.keys())
    placeholders = ", ".join("?" for _ in cols)
    update_clause = ", ".join(f"{k}=excluded.{k}" for k in fields.keys())
    sql = (
        f"INSERT INTO jobs ({', '.join(cols)}) VALUES ({placeholders}) "
        f"ON CONFLICT(source, source_id) DO UPDATE SET {update_clause} "
        f"RETURNING id"
    )
    with connect() as c:
        row = c.execute(sql, [source, source_id, *fields.values()]).fetchone()
        return row["id"]


def unscored_jobs():
    with connect() as c:
        return c.execute(
            "SELECT j.* FROM jobs j LEFT JOIN scores s ON s.job_id = j.id "
            "WHERE s.job_id IS NULL"
        ).fetchall()


def save_score(job_id: int, score: int, fit_summary: str, disqualified: bool,
               disqualify_reason: str | None, matched_skills: str, missing_skills: str):
    with connect() as c:
        c.execute(
            "INSERT INTO scores (job_id, score, fit_summary, disqualified, "
            "disqualify_reason, matched_skills, missing_skills) VALUES (?,?,?,?,?,?,?) "
            "ON CONFLICT(job_id) DO UPDATE SET score=excluded.score, "
            "fit_summary=excluded.fit_summary, disqualified=excluded.disqualified, "
            "disqualify_reason=excluded.disqualify_reason, matched_skills=excluded.matched_skills, "
            "missing_skills=excluded.missing_skills, scored_at=CURRENT_TIMESTAMP",
            (job_id, score, fit_summary, int(disqualified), disqualify_reason,
             matched_skills, missing_skills),
        )


def get_job(job_id: int):
    with connect() as c:
        return c.execute(
            "SELECT j.*, s.score, s.fit_summary, s.disqualified, s.disqualify_reason "
            "FROM jobs j LEFT JOIN scores s ON s.job_id = j.id WHERE j.id = ?",
            (job_id,),
        ).fetchone()


def upsert_application(job_id: int, **fields):
    with connect() as c:
        existing = c.execute(
            "SELECT id FROM applications WHERE job_id = ?", (job_id,)
        ).fetchone()
        if existing:
            sets = ", ".join(f"{k} = ?" for k in fields)
            c.execute(
                f"UPDATE applications SET {sets}, updated_at = CURRENT_TIMESTAMP "
                f"WHERE job_id = ?",
                (*fields.values(), job_id),
            )
            return existing["id"]
        cols = ["job_id"] + list(fields)
        c.execute(
            f"INSERT INTO applications ({', '.join(cols)}) VALUES "
            f"({', '.join('?' for _ in cols)})",
            (job_id, *fields.values()),
        )
        return c.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]


def ranked_jobs(threshold: int = 0, include_disqualified: bool = False, limit: int = 50):
    sql = (
        "SELECT j.id, j.source, j.company, j.title, j.location, j.url, "
        "s.score, s.fit_summary, s.disqualified, s.disqualify_reason, s.matched_skills "
        "FROM jobs j JOIN scores s ON s.job_id = j.id "
        "WHERE s.score >= ? "
    )
    if not include_disqualified:
        sql += "AND s.disqualified = 0 "
    sql += "ORDER BY s.score DESC LIMIT ?"
    with connect() as c:
        return c.execute(sql, (threshold, limit)).fetchall()
