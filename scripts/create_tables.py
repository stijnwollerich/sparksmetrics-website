"""Create database tables. Run from project root: python3 scripts/create_tables.py"""
from app import create_app
from app.models import db

app = create_app()
with app.app_context():
    db.create_all()
    print("Tables created.")
