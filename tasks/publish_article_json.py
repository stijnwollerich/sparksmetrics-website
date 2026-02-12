"""
Publish an article by generating a JSON spec via the LLM and rendering it to HTML,
then overwriting the existing template.

Usage:
  ./.venv/bin/python tasks/publish_article_json.py --slug 5_cro_mistakes_ecommerce_brands_make
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from pathlib import Path as _Path
import sys as _sys

# Ensure package import works when running as script
_root = _Path(__file__).resolve().parents[1]
if str(_root) not in _sys.path:
    _sys.path.insert(0, str(_root))

from tasks.auto_blog_from_youtube import (
    _load_env,
    expand_article_to_json_spec,
    render_article_from_spec,
    build_post_template,
)


def run(slug: str, dry_run: bool = False):
    project_root = Path(__file__).resolve().parents[1]
    _load_env(project_root)
    templates_dir = project_root / "app" / "templates"
    posts_path = project_root / "app" / "blog_posts.json"

    tpl_candidates = [templates_dir / f"blog_{slug}.html", templates_dir / f"blog_{slug.replace('-', '_')}.html"]
    tpl = None
    for c in tpl_candidates:
        if c.exists():
            tpl = c
            break
    if not tpl:
        raise SystemExit(f"Template not found for slug: {slug}")

    txt = tpl.read_text(encoding="utf-8")
    # extract inner article
    import re
    m = re.search(r'(<article[^>]*class=["\'][^"\']*blog-prose[^"\']*["\'][^>]*>)(.*?)(</article>)', txt, flags=re.I | re.S)
    if not m:
        raise SystemExit("No article block found")
    inner = m.group(2)
    # remove any JSON-LD script blocks or other scripts from the extracted inner HTML
    inner = re.sub(r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>.*?</script>', '', inner, flags=re.I | re.S)
    inner = re.sub(r'<script[^>]*>.*?</script>', '', inner, flags=re.I | re.S)

    # load post metadata if present (needed to derive better title)
    posts = []
    if posts_path.exists():
        data = json.loads(posts_path.read_text(encoding="utf-8"))
        posts = data.get("posts") if isinstance(data, dict) else data
    post_meta = next((p for p in posts if p.get("slug") == slug), {}) if posts else {}

    # derive a better title if current metadata title looks like a video id
    def _is_video_id_like(s: str) -> bool:
        if not s:
            return True
        s = s.strip()
        # typical YT id length 11 and uppercase/lower alnum
        return bool(re.fullmatch(r"[A-Za-z0-9_-]{8,20}", s)) and len(s) <= 20 and s.isupper()

    post_title = post_meta.get("title") or ""
    # if title is missing or looks like an id, try YouTube oEmbed to get the real title
    if _is_video_id_like(post_title) and post_meta.get("video_id"):
        try:
            import urllib.request as _ur
            import json as _json

            vid = post_meta.get("video_id")
            oembed_url = f"https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={vid}&format=json"
            with _ur.urlopen(_ur.Request(oembed_url, headers={"User-Agent": "SparksmetricsBot/1.0"}), timeout=10) as resp:
                data = _json.load(resp)
                post_title = data.get("title") or post_title
        except Exception:
            # ignore failures and keep existing title
            pass

    # (post_meta is now available)

    # Ask LLM for JSON spec and render (with fallback)
    spec = None
    rendered = None
    # If the existing inner contains JSON-LD or looks corrupted, avoid reusing it for spec generation
    existing_for_spec = inner
    if '{"@context"' in (inner or "") or 'application/ld+json' in (inner or ""):
        existing_for_spec = ""

    try:
        spec = expand_article_to_json_spec(title=post_title or slug.replace("-", " ").title(), transcript=post_meta.get("transcript", "") or "", existing_html=existing_for_spec)
        rendered = render_article_from_spec(spec)
    except Exception as e:
        # If structured spec generation failed, use deterministic rich spec generator
        from tasks.auto_blog_from_youtube import _build_rich_spec_from_text

        print("Structured JSON spec failed:", e, "— using deterministic rich spec")
        spec = _build_rich_spec_from_text(title=post_meta.get("title") or slug.replace("-", " ").title(), transcript=post_meta.get("transcript", "") or "", existing_html=inner)
        rendered = render_article_from_spec(spec)
        if spec.get("description"):
            post_meta["description"] = spec.get("description")

    # Show preview of the generated spec (JSON) before rendering/writing
    print("=== Generated JSON spec preview ===")
    try:
        print(json.dumps(spec, indent=2, ensure_ascii=False))
    except Exception:
        print(str(spec))
    print("=== End spec preview ===")

    # Build post dict
    post = {
        "slug": slug,
        "title": spec.get("title") or post_meta.get("title") or slug.replace("_", " ").replace("-", " ").title(),
        "description": spec.get("description") or post_meta.get("description") or "",
        "published_date": post_meta.get("published_date") or post_meta.get("updated_date") or "11 Feb 2026",
        "updated_date": post_meta.get("updated_date") or post_meta.get("published_date") or "11 Feb 2026",
        "reading_time": post_meta.get("reading_time") or "10 min read",
        "category": post_meta.get("category") or "CRO",
        "template": tpl.name,
        "video_id": post_meta.get("video_id") or "",
    }

    # Build full template and write
    template_text = build_post_template(video_id=post.get("video_id") or "", post=post, article_html=rendered)
    if dry_run:
        print("[dry-run] Would overwrite template:", tpl)
    else:
        tpl.write_text(template_text, encoding="utf-8")
        print("Wrote template:", tpl)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--slug", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    run(args.slug, dry_run=args.dry_run)

