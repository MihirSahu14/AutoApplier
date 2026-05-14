from pathlib import Path
from pypdf import PdfReader

from .paths import CACHE_DIR
CACHE = CACHE_DIR / "resume.txt"


def extract_text(pdf_path: str | Path) -> str:
    pdf_path = Path(pdf_path)
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    if CACHE.exists() and CACHE.stat().st_mtime >= pdf_path.stat().st_mtime:
        return CACHE.read_text(encoding="utf-8")
    reader = PdfReader(str(pdf_path))
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    CACHE.write_text(text, encoding="utf-8")
    return text
