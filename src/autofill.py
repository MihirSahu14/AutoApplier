"""Open a job application URL in a real browser, prefill what we can, and
hand control back to the user.

Design notes:
- Uses Playwright's *persistent* Chromium context (user_data_dir under
  `data/browser_profile/`) so logins (LinkedIn, Greenhouse, etc.) survive
  across runs.  Don't reset that dir unless you want to log in again.
- Runs in a background thread so the FastAPI request returns instantly.
  The thread blocks until the user closes the browser, then cleans up.
- Never clicks submit.  Always leaves the final review + click to the user.
"""
import re
import threading
import time
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent

# ---- field-matching heuristics ------------------------------------------------
# Each kind maps to regex patterns we look for in the input's label, name,
# id, placeholder, or aria-label.  Order in the dict = priority (first match wins).

TEXT_PATTERNS: dict[str, list[str]] = {
    "first_name":  [r"\bfirst[\s_-]*name\b", r"\bgiven[\s_-]*name\b", r"\bforename\b"],
    "last_name":   [r"\blast[\s_-]*name\b", r"\bfamily[\s_-]*name\b", r"\bsurname\b"],
    "full_name":   [r"\bfull[\s_-]*name\b", r"\byour[\s_-]*name\b", r"\bapplicant[\s_-]*name\b", r"^name$"],
    "email":       [r"e[\s_-]*mail"],
    "phone":       [r"\bphone\b", r"\bmobile\b", r"\btelephone\b", r"\btel\b"],
    "linkedin":    [r"linkedin"],
    "github":      [r"github"],
    "portfolio":   [r"portfolio", r"personal[\s_-]*(?:site|website)", r"^website$", r"^url$"],
    "location":    [r"current[\s_-]*city", r"current[\s_-]*location", r"\bcity\b", r"\baddress\b", r"\blocation\b"],
}

FILE_PATTERNS: dict[str, list[str]] = {
    "resume": [r"\bresume\b", r"\bcv\b", r"curriculum"],
    "cover":  [r"cover[\s_-]*letter"],
}

# Yes/no questions we can confidently answer from profile data.
YESNO_PATTERNS: list[tuple[str, str, str]] = [
    # (regex on question text, answer when needs_sponsorship=True, when False)
    (r"sponsorship|visa|work[\s_-]*auth", "yes", "no"),
    (r"\bus\s+citizen", "no", "yes"),  # we treat F-1/needs-sponsorship as not a citizen
]


def _split_name(full: str) -> tuple[str, str]:
    parts = (full or "").strip().split()
    if not parts:
        return "", ""
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], " ".join(parts[1:])


def _values_from_profile(p: dict) -> dict:
    first, last = _split_name(p["contact"]["name"])
    return {
        "first_name": first,
        "last_name":  last,
        "full_name":  p["contact"]["name"],
        "email":      p["contact"]["email"],
        "phone":      p["contact"]["phone"],
        "linkedin":   p["contact"]["linkedin"],
        "github":     p["contact"]["github"],
        "portfolio":  p["contact"]["portfolio"],
        "location":   p["contact"]["location"],
    }


def _match(blob: str, table: dict[str, list[str]]) -> Optional[str]:
    blob = blob.lower()
    for kind, patterns in table.items():
        for pat in patterns:
            if re.search(pat, blob):
                return kind
    return None


# ---- the page-walker ---------------------------------------------------------

def _fill_page(page, values: dict, resume_path: Path, cover_path: Optional[Path],
               needs_sponsorship: bool) -> dict:
    """Returns stats: {'filled': n, 'uploaded': n, 'yesno': n, 'skipped': n}."""
    stats = {"filled": 0, "uploaded": 0, "yesno": 0, "skipped": 0}

    try:
        page.wait_for_selector("input, textarea, select", timeout=8000)
    except Exception:
        pass

    inputs = page.query_selector_all("input, textarea")
    for el in inputs:
        try:
            input_type = (el.get_attribute("type") or "text").lower()
            if input_type in ("hidden", "submit", "button", "image", "reset"):
                continue

            name = el.get_attribute("name") or ""
            id_ = el.get_attribute("id") or ""
            placeholder = el.get_attribute("placeholder") or ""
            aria_label = el.get_attribute("aria-label") or ""

            # Resolve label
            label_text = ""
            if id_:
                lab = page.query_selector(f'label[for="{id_}"]')
                if lab:
                    label_text = (lab.inner_text() or "").strip()
            if not label_text:
                label_text = el.evaluate(
                    "e => { const l = e.closest('label'); return l ? l.innerText : ''; }"
                ) or ""

            blob = " ".join(filter(None, [label_text, name, id_, placeholder, aria_label]))

            # File inputs
            if input_type == "file":
                kind = _match(blob, FILE_PATTERNS)
                path = resume_path if kind == "resume" else (cover_path if kind == "cover" else None)
                if path and path.exists():
                    try:
                        el.set_input_files(str(path))
                        stats["uploaded"] += 1
                    except Exception:
                        stats["skipped"] += 1
                continue

            # Skip checkbox/radio here; handled below via groups
            if input_type in ("checkbox", "radio"):
                continue

            # Skip pre-filled fields
            try:
                cur = el.input_value()
            except Exception:
                cur = ""
            if cur:
                continue

            kind = _match(blob, TEXT_PATTERNS)
            if kind and values.get(kind):
                el.fill(values[kind])
                stats["filled"] += 1
        except Exception:
            stats["skipped"] += 1
            continue

    # Yes/no questions: detect by scanning for a question and the radio/select
    # within the same form-row.  Best effort.
    try:
        labels = page.query_selector_all("label, legend, .question, .field-label")
        for lab in labels:
            try:
                text = (lab.inner_text() or "").strip()
                if not text or len(text) > 200:
                    continue
                for pat, ans_yes, ans_no in YESNO_PATTERNS:
                    if re.search(pat, text, re.IGNORECASE):
                        target = ans_yes if needs_sponsorship else ans_no
                        # Find the nearest input within ancestor form-row
                        container = lab.evaluate_handle(
                            "e => e.closest('fieldset, .form-row, .field, .question, div')"
                        )
                        if not container:
                            break
                        # Try radio with matching value
                        radios = page.evaluate(
                            "(c) => [...c.querySelectorAll('input[type=radio]')]"
                            ".map(r => ({ id: r.id, value: r.value, name: r.name }))",
                            container,
                        )
                        for r in radios:
                            v = (r["value"] or "").strip().lower()
                            if v == target or v.startswith(target):
                                sel = f'input[type=radio][name="{r["name"]}"][value="{r["value"]}"]'
                                page.check(sel)
                                stats["yesno"] += 1
                                break
                        break
            except Exception:
                continue
    except Exception:
        pass

    return stats


# ---- public entry: spawn the browser thread ---------------------------------

def launch_autofill_thread(url: str, profile: dict, resume_path: Path,
                           cover_path: Optional[Path]) -> threading.Thread:
    """Spawn a background thread that opens a non-headless browser, fills
    fields, and stays open until the user closes it.  Returns the thread.
    """
    def _run():
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            print("[autofill] playwright not installed. Run: pip install playwright && playwright install chromium")
            return

        user_dir = ROOT / "data" / "browser_profile"
        user_dir.mkdir(parents=True, exist_ok=True)
        values = _values_from_profile(profile)
        needs_sponsorship = bool(profile.get("visa", {}).get("needs_sponsorship"))

        try:
            with sync_playwright() as pw:
                ctx = pw.chromium.launch_persistent_context(
                    user_data_dir=str(user_dir),
                    headless=False,
                    viewport=None,
                    args=["--start-maximized"],
                )
                page = ctx.pages[0] if ctx.pages else ctx.new_page()
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=60_000)
                except Exception as e:
                    print(f"[autofill] navigation failed: {e}")
                try:
                    stats = _fill_page(page, values, resume_path, cover_path, needs_sponsorship)
                    print(f"[autofill] {stats}")
                except Exception as e:
                    print(f"[autofill] fill error: {e}")
                # Block until user closes all pages
                while True:
                    try:
                        if not ctx.pages:
                            break
                        time.sleep(2)
                    except Exception:
                        break
                try:
                    ctx.close()
                except Exception:
                    pass
        except Exception as e:
            print(f"[autofill] fatal: {e}")

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return t
