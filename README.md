# Auto Job Applier

End-to-end pipeline that finds, rates, and (eventually) applies to software roles
matched to a personal resume + targeting profile.

Currently implemented (v0.1):
- Job ingestion from Hacker News "Who is hiring?"
- Claude-based fit scoring against resume + targets
- Hard-filter disqualification (sponsorship, citizenship, salary floor)
- SQLite ledger of all jobs and scores
- Excel export with Applications tracker, dropdown statuses, summary tab
- Daily USD budget cap on Anthropic API spend

## Setup

```bash
# Backend
pip install -r requirements.txt
cp .env.example .env                  # fill in API keys
cp config.example.yaml config.yaml    # fill in your name, resume path, targets
python cli.py init

# Frontend (one-time)
cd frontend && npm install && cd ..
```

## Run the Web UI

Two terminals:

```bash
# Terminal 1 — backend (http://localhost:8765)
python webapp.py

# Terminal 2 — frontend (http://localhost:5173)
cd frontend && npm run dev
```

Open http://localhost:5173. You get a job list with filters, score pills, and
one-click buttons for: ingest HN, prefilter, score, export Excel, generate
tailored package, open job page, download resume/cover, update status & notes.

## Usage (CLI, still works)

```bash
python cli.py ingest --source hn   # pull latest HN Who-is-hiring
python cli.py prefilter            # free regex DQ pass — no API spend
python cli.py score                # Claude scores survivors (Haiku, cheap)
python cli.py rank                 # show top jobs in terminal
python cli.py show <id>            # full job + breakdown
python cli.py apply <id>           # tailored resume + cover letter -> data/output/<id>_<co>/
python cli.py export               # write data/JobTracker.xlsx
python cli.py budget               # show today's spend per stage
```

## Tailoring (`apply`)

`python cli.py apply 7` produces, into `data/output/7_neuralink/`:

- `Resume_<name>.docx` — 1-page tailored resume.  Bullets are **reordered and
  lightly rephrased**, never fabricated.  Skills are reordered to lead with
  matched ones.
- `CoverLetter_<name>_<company>.docx` — 3-paragraph cover letter (~280 words),
  grounded in resume facts only.
- `tailored_resume.json` and `cover_letter.txt` for inspection / further edits.

The application is recorded in the `applications` table; the next `export` run
puts the file paths in the **Applications** tab of `JobTracker.xlsx` next to
the job, with status defaulted to "To apply".

## Three-tier funnel

To keep credits focused on tailoring + outreach, scoring is layered:

1. **Free regex prefilter** — drops jobs with no-sponsorship clauses, citizenship requirements, security clearances, senior-only titles, or non-engineering roles. $0.
2. **Haiku 4.5 scoring** — fast cheap fit scoring on survivors (~$0.003/job).
3. **Sonnet 4.5 generation** — reserved for the high-value work: resume tailoring, cover letters, cold emails on jobs you actually choose to apply to.

Each stage has its own slice of the daily cap (`config.yaml` → `budget.stage_caps`),
so high-volume scoring can never starve the tailoring budget.

## Config (`config.yaml`)

- `profile.*` — name, contact, resume path
- `visa.disqualify_if` — substrings that auto-reject a job
- `targets.*` — roles, company size, salary floor, locations
- `scoring.threshold` — min score to surface in `rank`
- `budget.daily_usd` — hard cap on Anthropic spend per day

## Roadmap

- More job sources: Greenhouse, Lever, Ashby, Wellfound, YC WAAS, Jobright
- Resume tailoring (1-page DOCX) + cover letter per job
- ATS-specific autofillers (Playwright)
- Founder/HM lookup (Hunter, Apollo) + cold email drafts in Gmail
