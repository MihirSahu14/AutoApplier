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
pip install -r requirements.txt
cp .env.example .env             # fill in API keys
cp config.example.yaml config.yaml  # fill in your name, resume path, targets
python cli.py init
```

## Usage

```bash
python cli.py ingest --source hn   # pull latest HN Who-is-hiring
python cli.py prefilter            # free regex DQ pass — no API spend
python cli.py score                # Claude scores survivors (Haiku, cheap)
python cli.py rank                 # show top jobs in terminal
python cli.py show <id>            # full job + breakdown
python cli.py export               # write data/JobTracker.xlsx
python cli.py budget               # show today's spend per stage
```

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
