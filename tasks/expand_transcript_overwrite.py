"""
Expand transcript using OpenAI and overwrite the post template with full HTML.

Usage:
  ./.venv/bin/python tasks/expand_transcript_overwrite.py --slug 5-cro-mistakes-ecommerce-brands-make --transcript-file tasks/_transcript_qed0zrqFYeg.txt
"""
from __future__ import annotations

import argparse
from pathlib import Path
import json
from pathlib import Path as _Path
import sys as _sys

# Ensure package imports work
_root = _Path(__file__).resolve().parents[1]
if str(_root) not in _sys.path:
    _sys.path.insert(0, str(_root))

from tasks.auto_blog_from_youtube import _load_env, expand_article_with_openai, build_post_template


def run(slug: str, transcript_file: Path, overwrite: bool = True):
    project_root = Path(__file__).resolve().parents[1]
    _load_env(project_root)
    tpl_name = f"blog_{slug}.html"
    templates_dir = project_root / "app" / "templates"
    tpl_path = templates_dir / tpl_name

    transcript = transcript_file.read_text(encoding="utf-8")
    title = slug.replace("-", " ").title()

    # Try expand with OpenAI (this requests a full HTML fragment)
    try:
        expanded = expand_article_with_openai(title=title, transcript=transcript, existing_html="", model=(__import__("os").environ.get("OPENAI_MODEL") or "gpt-4.1-mini"))
    except Exception as e:
        raise SystemExit(f"OpenAI expansion failed: {e}")

    html = expanded.get("html") or ""
    desc = expanded.get("description") or ""

    post = {
        "slug": slug,
        "title": title,
        "description": desc or title,
        "published_date": "11 Feb 2026",
        "updated_date": "11 Feb 2026",
        "reading_time": "10 min read",
        "category": "CRO",
        "template": tpl_name,
        "video_id": "",
    }

    template_text = build_post_template(video_id=post.get("video_id") or "", post=post, article_html=html)
    if overwrite:
        tpl_path.write_text(template_text, encoding="utf-8")
        print("Wrote template:", tpl_path)
    else:
        print("[dry-run] Would write template:", tpl_path)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--slug", required=True)
    parser.add_argument("--transcript-file", required=True)
    parser.add_argument("--no-overwrite", action="store_true")
    args = parser.parse_args()
    run(args.slug, Path(args.transcript_file), overwrite=not args.no_overwrite)

