"""Create database tables. Run from project root: python3 scripts/create_tables.py"""
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
        line = line.strip().replace("\r", "")
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            k, v = key.strip(), value.strip().strip("'\"").replace("\r", "")
            if k and v:
                os.environ[k] = v

from app import create_app
from app.models import db

app = create_app()
with app.app_context():
    db.create_all()
    print("Tables created.")
