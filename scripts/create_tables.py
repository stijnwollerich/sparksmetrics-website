"""Create database tables. Run from project root: python3 scripts/create_tables.py"""
import sys
from pathlib import Path

# Ensure project root is on sys.path when run as python3 scripts/create_tables.py
_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from app import create_app
from app.models import db

app = create_app()
with app.app_context():
    db.create_all()
    print("Tables created.")
