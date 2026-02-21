"""Add website_url column to leads table. Run once: python3 tasks/add_leads_website_url.py"""
import os
import sys
from pathlib import Path

_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

_env_path = _root / ".env"
if _env_path.exists():
    raw = _env_path.read_text(encoding="utf-8", errors="replace")
    for line in raw.splitlines():
        line = line.strip().replace("\r", "").strip("\ufeff")
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            k, v = key.strip(), value.strip().strip("'\"").replace("\r", "")
            if k and v:
                os.environ[k] = v
if not os.environ.get("DATABASE_URL"):
    print("ERROR: DATABASE_URL not set.")
    sys.exit(1)

from app import create_app
from app.models import db

app = create_app()
with app.app_context():
    db.session.execute(db.text("ALTER TABLE leads ADD COLUMN IF NOT EXISTS website_url VARCHAR(500) NULL"))
    db.session.commit()
    print("Column leads.website_url added (or already exists).")
