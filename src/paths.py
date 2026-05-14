"""All on-disk paths used by the app, rooted at DATA_DIR.

Override DATA_DIR with the env var `AJA_DATA_DIR` (used on Render to point at
the persistent disk mount, e.g. `/var/data`).
"""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("AJA_DATA_DIR") or (ROOT / "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

DB_PATH             = DATA_DIR / "jobs.db"
PROFILE_PATH        = DATA_DIR / "profile.json"
CACHE_DIR           = DATA_DIR / "cache"
OUTPUT_DIR          = DATA_DIR / "output"
RESUMES_DIR         = DATA_DIR / "resume"
BROWSER_PROFILE_DIR = DATA_DIR / "browser_profile"
LEDGER_PATH         = DATA_DIR / "spend_ledger.json"
TRACKER_XLSX        = DATA_DIR / "JobTracker.xlsx"
COMPANIES_YAML      = DATA_DIR / "companies.yaml"
