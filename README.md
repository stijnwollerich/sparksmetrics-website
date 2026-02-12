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

## Blog automation (YouTube → Blog → Slack)

This repo supports a cron-friendly script that creates a new blog post when a new YouTube video is published.

### What it does

- Checks your channel RSS feed (no YouTube API key required)
- If a new video is found (not already present in `app/blog_posts.json`), it:
  - Fetches a transcript (requires captions)
  - Creates a new blog template in `app/templates/`
  - Adds the post metadata to `app/blog_posts.json` (so it appears on `/blog` and `/sitemap.xml`)
  - Sends you a Slack message with the new post link

### Setup

1. Ensure dependencies are installed (includes `youtube-transcript-api`):

```bash
pip install -r requirements.txt
```

2. Set these env vars in `.env` (see `.env.example`):
- `YOUTUBE_CHANNEL_ID` (e.g. `UCkwylcLXJiV-kQxCZMRR-tw`)
- `SLACK_WEBHOOK_URL` (optional but recommended)
- `SITE_BASE_URL` (for Slack links; defaults to `https://sparksmetrics.com`)
- `OPENAI_API_KEY` (optional; enables higher-quality writing)
 - `SUPADATA_KEY` (optional; preferred transcript provider — no YouTube captions required in many cases)
 - `OPENAI_API_KEY` or `OPEN_AI_KEY` (optional; enables higher-quality writing)

3. Run once (safe; creates at most 1 post per run):

```bash
python tasks/auto_blog_from_youtube.py --channel UCkwylcLXJiV-kQxCZMRR-tw
```

### Cron example

Run every hour:

```bash
0 * * * * cd /path/to/sparksmetrics-website && /path/to/sparksmetrics-website/.venv/bin/python tasks/auto_blog_from_youtube.py --channel UCkwylcLXJiV-kQxCZMRR-tw
```

Notes:
- If a video has no transcript available, the script will **skip it** and (optionally) notify Slack instead of failing the cron.
