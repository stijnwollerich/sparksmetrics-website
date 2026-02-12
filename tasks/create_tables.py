"""Create database tables. Run from project root: python3 tasks/create_tables.py"""
import os
import sys
from pathlib import Path

_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

# Load .env from project root first (same pattern as Upwork run.mjs) so DATABASE_URL is set before app imports
_env_path = _root / ".env"
if _env_path.exists():
    raw = _env_path.read_text(encoding="utf-8", errors="replace")
    for line in raw.splitlines():
        line = line.strip().replace("\r", "").strip("\ufeff")  # BOM
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            k, v = key.strip(), value.strip().strip("'\"").replace("\r", "")
            if k and v:
                os.environ[k] = v
    # Fallback: ensure DATABASE_URL from any line containing DATABASE_URL=
    if not os.environ.get("DATABASE_URL"):
        for line in raw.splitlines():
            if "DATABASE_URL=" in line:
                v = line.split("=", 1)[1].strip().strip("'\"").replace("\r", "")
                if v:
                    os.environ["DATABASE_URL"] = v
                break
if not os.environ.get("DATABASE_URL"):
    print("ERROR: DATABASE_URL not set. Check that", _env_path, "exists and contains DATABASE_URL=postgresql://...")
    sys.exit(1)

from app import create_app
from app.models import db

app = create_app()
with app.app_context():
    db.create_all()
    print("Tables created.")

