"""Auto Job Applier CLI."""
import json
import typer
from rich.console import Console
from rich.table import Table
from rich.progress import track

from src import config as cfg_mod
from src import db, resume, budget, prefilter, export as export_mod
from src.sources import hn
from src.scorer import score_job, build_profile_block

app = typer.Typer(help="Auto Job Applier")
console = Console()


@app.command()
def init():
    """Initialize the SQLite DB."""
    db.init_db()
    console.print("[green]DB initialized[/green]")


@app.command()
def ingest(source: str = "hn"):
    """Pull jobs from a source into the DB."""
    db.init_db()
    cfg = cfg_mod.load()
    if source == "hn":
        months = cfg["sources"]["hn_who_is_hiring"]["months_back"]
        console.print(f"[cyan]Fetching HN Who-is-hiring (last {months} months)...[/cyan]")
        rows = hn.fetch(months_back=months)
        for r in rows:
            db.upsert_job(
                source="hn",
                source_id=r["source_id"],
                company=r["company"],
                title=r["title"],
                location=r["location"],
                url=r["url"],
                description=r["description"],
                posted_at=r["posted_at"],
            )
        console.print(f"[green]Ingested {len(rows)} jobs from HN[/green]")
    else:
        console.print(f"[red]Unknown source: {source}[/red]")
        raise typer.Exit(1)


@app.command(name="prefilter")
def prefilter_cmd():
    """Run free regex disqualifiers over unscored jobs (no API spend)."""
    jobs = db.unscored_jobs()
    if not jobs:
        console.print("[yellow]No unscored jobs[/yellow]")
        return
    dq = 0
    for j in track(jobs, description="Pre-filtering"):
        passed, reason = prefilter.check(dict(j))
        if not passed:
            db.save_score(
                job_id=j["id"],
                score=0,
                fit_summary=f"[prefilter] {reason}",
                disqualified=True,
                disqualify_reason=reason,
                matched_skills=json.dumps([]),
                missing_skills=json.dumps([]),
            )
            dq += 1
    console.print(
        f"[green]Pre-filter done.[/green] Disqualified [bold]{dq}[/bold] of "
        f"{len(jobs)} ({100*dq/len(jobs):.0f}%) for free. "
        f"{len(jobs) - dq} remaining will go to Claude."
    )


@app.command()
def score(limit: int = 0):
    """Score every unscored job in the DB. limit=0 means all."""
    cfg = cfg_mod.load()
    resume_text = resume.extract_text(cfg["profile"]["resume_pdf"])
    profile = build_profile_block(cfg, resume_text)
    model = cfg["scoring"]["model"]
    stage_caps = cfg["budget"]["stage_caps"]
    pricing = cfg["pricing"]

    jobs = db.unscored_jobs()
    if limit:
        jobs = jobs[:limit]
    if not jobs:
        console.print("[yellow]No unscored jobs[/yellow]")
        return

    spent = budget.stage_spent_usd("scoring")
    remaining = budget.stage_remaining_usd("scoring", stage_caps)
    console.print(
        f"[cyan]Scoring up to {len(jobs)} jobs with {model}. "
        f"Scoring stage today: ${spent:.4f} / ${stage_caps['scoring']:.2f} "
        f"(${remaining:.4f} remaining)[/cyan]"
    )
    stopped_for_budget = False
    for j in track(jobs, description="Scoring"):
        try:
            result = score_job(
                profile, dict(j), model=model, stage_caps=stage_caps, pricing=pricing,
            )
        except budget.BudgetExceeded as e:
            console.print(f"[yellow]{e}[/yellow]")
            stopped_for_budget = True
            break
        except Exception as e:
            console.print(f"[red]error on job {j['id']}: {e}[/red]")
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
    final = budget.stage_spent_usd("scoring")
    if stopped_for_budget:
        console.print(f"[yellow]Stopped early. Scoring spend today: ${final:.4f}[/yellow]")
    else:
        console.print(f"[green]Scoring complete. Scoring spend today: ${final:.4f}[/green]")


@app.command()
def rank(threshold: int | None = None, limit: int = 30, all: bool = False):
    """Show top-ranked jobs."""
    cfg = cfg_mod.load()
    th = threshold if threshold is not None else cfg["scoring"]["threshold"]
    rows = db.ranked_jobs(threshold=th, include_disqualified=all, limit=limit)
    if not rows:
        console.print("[yellow]No jobs above threshold[/yellow]")
        return

    table = Table(show_lines=False)
    table.add_column("ID", justify="right")
    table.add_column("Score", justify="right", style="bold")
    table.add_column("Company")
    table.add_column("Title")
    table.add_column("Location")
    table.add_column("Why", overflow="fold", max_width=55)
    for r in rows:
        score_color = "green" if r["score"] >= 80 else ("yellow" if r["score"] >= 70 else "white")
        table.add_row(
            str(r["id"]),
            f"[{score_color}]{r['score']}[/{score_color}]",
            (r["company"] or "")[:28],
            (r["title"] or "")[:32],
            (r["location"] or "")[:18],
            r["fit_summary"] or "",
        )
    console.print(table)
    console.print(f"\n[dim]Showing {len(rows)} jobs with score >= {th}[/dim]")


@app.command()
def show(job_id: int):
    """Print full details + URL for a job."""
    with db.connect() as c:
        row = c.execute(
            "SELECT j.*, s.score, s.fit_summary, s.matched_skills, s.missing_skills, "
            "s.disqualified, s.disqualify_reason "
            "FROM jobs j LEFT JOIN scores s ON s.job_id = j.id WHERE j.id = ?",
            (job_id,),
        ).fetchone()
    if not row:
        console.print(f"[red]No job {job_id}[/red]")
        raise typer.Exit(1)
    console.rule(f"Job {job_id}: {row['company']} — {row['title']}")
    console.print(f"[bold]URL:[/bold] {row['url']}")
    console.print(f"[bold]Location:[/bold] {row['location']}")
    console.print(f"[bold]Score:[/bold] {row['score']} — {row['fit_summary']}")
    if row["disqualified"]:
        console.print(f"[red]Disqualified: {row['disqualify_reason']}[/red]")
    console.print(f"[bold]Matched:[/bold] {row['matched_skills']}")
    console.print(f"[bold]Missing:[/bold] {row['missing_skills']}")
    console.rule("Description")
    console.print(row["description"])


@app.command()
def export():
    """Write all jobs + applications tracker to data/JobTracker.xlsx."""
    path = export_mod.export()
    console.print(f"[green]Wrote {path}[/green]")


@app.command(name="budget")
def budget_cmd():
    """Show today's API spend per stage."""
    cfg = cfg_mod.load()
    caps = cfg["budget"]["stage_caps"]
    daily = cfg["budget"]["daily_usd"]

    table = Table(title="Today's spend by stage")
    table.add_column("Stage")
    table.add_column("Spent", justify="right")
    table.add_column("Cap", justify="right")
    table.add_column("Remaining", justify="right")
    for stage, cap in caps.items():
        spent = budget.stage_spent_usd(stage)
        rem = budget.stage_remaining_usd(stage, caps)
        color = "red" if rem == 0 else ("yellow" if rem < cap * 0.2 else "green")
        table.add_row(stage, f"${spent:.4f}", f"${cap:.2f}", f"[{color}]${rem:.4f}[/{color}]")
    table.add_row(
        "[bold]TOTAL[/bold]",
        f"[bold]${budget.today_spent_usd():.4f}[/bold]",
        f"[bold]${daily:.2f}[/bold]",
        "",
    )
    console.print(table)


if __name__ == "__main__":
    app()
