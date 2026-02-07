# Sparksmetrics Website

Custom Flask website (replacing WordPress).

## Setup

1. Create a virtual environment and install dependencies:

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate   # On Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   ```

2. Copy `.env.example` to `.env` and set `SECRET_KEY` (and optionally `FLASK_DEBUG=1` for development).

3. Run the development server:

   ```bash
   flask run
   # or
   python run.py
   ```

   Open http://127.0.0.1:5000

## Project structure

```
sparksmetrics-website/
├── app/
│   ├── __init__.py      # App factory
│   ├── config.py        # Configuration
│   ├── routes/          # Blueprints (main, etc.)
│   ├── templates/       # Jinja2 HTML templates
│   └── static/          # CSS, JS, images
├── requirements.txt
├── run.py               # Dev server entry point
├── .env.example
└── README.md
```

## Production

Run with Gunicorn:

```bash
gunicorn -w 4 -b 0.0.0.0:5000 "run:app"
```

Set `FLASK_DEBUG=0` and a strong `SECRET_KEY` in production.
