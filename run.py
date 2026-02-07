"""Run the Flask development server."""
import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env from project root (directory containing run.py)
_env = Path(__file__).resolve().parent / ".env"
load_dotenv(_env)

from app import create_app

app = create_app()

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5001)),
        debug=app.config["DEBUG"],
    )
