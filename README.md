# Auto Job Applier

End-to-end pipeline that finds, rates, tailors, and tracks job applications
based on the user's resume and targeting profile.  Works for anyone — first
launch walks you through a setup wizard.

Implemented:
- 5-step **setup wizard** (web UI): contact info, resume upload OR
  free-form experience description, target roles/locations/salary, visa
  status + auto-disqualifiers, API key.  No code edits needed.
- Job ingestion from Hacker News "Who is hiring?"
- Three-tier scoring funnel: free regex prefilter → Haiku scoring →
  Sonnet tailoring + cover letters
- 1-page tailored resume + personal cover letter per job (.docx + JSON +
  plain text)
- SQLite + Excel tracker with editable status / notes / paths
- Daily USD budget caps split by stage (scoring / tailoring / outreach) so
  bulk scoring can't drain the tailoring budget
- React + TypeScript + Tailwind web UI with toasts, filters, score pills,
  empty states, settings page

## Setup (any user, no code edits required)

```bash
# Backend
pip install -r requirements.txt
python -m playwright install chromium    # for the autofill feature
cp config.example.yaml config.yaml       # only app-level knobs (models, budget)

# Frontend (one-time)
cd frontend && npm install && cd ..
```

## Run the Web UI

Two terminals:

```bash
# Terminal 1 — backend  (http://localhost:8765)
python webapp.py

# Terminal 2 — frontend (http://localhost:5173)
cd frontend && npm run dev
```

Open <http://localhost:5173>.  On first launch you'll be sent to **/setup** —
a 5-step wizard that collects:

1. Contact info (name, email, phone, LinkedIn, GitHub, portfolio, location).
2. Background: **upload a resume PDF** *or* describe your experience in a
   text box (works for people without a polished resume yet).
3. Targets: roles, salary floor, company size, locations OK / preferred.
4. Visa status + auto-disqualify phrases (e.g. "US citizen required").
5. Anthropic API key (required) + optional Hunter / Apollo / SerpAPI keys.

Everything is stored in `data/profile.json` (gitignored).  After setup you
land on the job list with one-click buttons for ingest, prefilter, score,
generate tailored package, download resume/cover, open job page, update
status, and export to Excel.  Edit anything later from the ⚙ Settings page.

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

## Deploy (Vercel + Render)

### Privacy model

- Nothing personal is in this git repo (resume PDF, API keys, contact info — all gitignored under `data/` + `.env`).
- On the cloud deploy, the backend's `AJA_DATA_DIR=/tmp/aja-data` is **ephemeral** — wiped on every container restart.
- Your profile + API keys are kept in your browser's `localStorage`. On a cold start the frontend auto-pushes them back to the server. The deploy itself stores **zero** durable user data.
- The server's API keys are whatever **you** type into Setup — there are none baked into `render.yaml` or env vars.

### What works in the cloud

| Feature | Works? |
|---|---|
| Ingest / prefilter / score / rank | ✅ |
| Tailored resume + cover letter | ✅ |
| Founder lookup + cold email drafts | ✅ |
| Gmail / mailto buttons | ✅ |
| Excel export download | ✅ |
| Playwright autofill | ❌ remote container can't open a browser on your laptop |
| Profile + jobs survive page refresh | ✅ profile via browser localStorage; jobs are re-ingested on demand |
| Profile + jobs survive backend cold-start | ⚠️ profile auto-restored from your browser; ingested jobs/scores reset and need re-running |

The autofill button still works when you run the backend locally — only the
remote deploy disables it.

### 1. Backend → Render

1. Push to GitHub (this repo is already there).
2. Render dashboard → **New → Blueprint**, point at the repo. It picks up
   `render.yaml` and creates a **free** Web Service. No paid disk, no API
   keys baked in — `AJA_DATA_DIR` points at `/tmp/aja-data` (ephemeral).
3. Render → service → **Environment** → set `FRONTEND_ORIGIN` after step 2 below.
   That's the only env var you need to set.
4. Wait for first deploy. Copy the service URL (e.g. `https://auto-job-applier-api.onrender.com`).

### 2. Frontend → Vercel

1. Vercel dashboard → **New Project** → import the same GitHub repo.
2. Settings → **Root Directory: `frontend`** (this is critical — Vercel will
   auto-detect Vite once you point it at the subfolder).
3. **Environment Variables** → add
   `VITE_API_BASE = https://<your-render-url>` (no trailing slash).
4. Deploy. Note the resulting URL (e.g. `https://aja.vercel.app`).
5. Back in Render → update `FRONTEND_ORIGIN` to that Vercel URL, save (it
   redeploys automatically).

### 3. First-run setup

Visit the Vercel URL. You'll be redirected to `/setup` because the persistent
disk starts empty. Walk the 5-step wizard (resume, targets, API key). Everything
persists from that point on.

### Notes & gotchas

- **Cold starts.** Render free spins down after 15 min idle. First request after
  that takes ~30 s. Upgrade plan or ping with a cron job if you hate it.
- **Background jobs survive the request** but get killed if the container
  restarts. Don't kick off a 10-min score on free tier and immediately wander
  off for an hour — finish what you start.
- **Long-running scores** count toward Render's 750 hrs/mo free.
- **No multi-user auth.** Anyone who hits your Vercel URL sees your profile and
  jobs. Either keep the URL private or add auth (Clerk/Auth0 in front).

## Roadmap

- More job sources: Greenhouse, Lever, Ashby, Wellfound, YC WAAS, Jobright
- Resume tailoring (1-page DOCX) + cover letter per job
- ATS-specific autofillers (Playwright)
- Founder/HM lookup (Hunter, Apollo) + cold email drafts in Gmail
