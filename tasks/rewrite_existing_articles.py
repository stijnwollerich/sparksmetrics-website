"""
Rewrite existing blog articles to match the site's SEO checklist.

Usage (dry-run):
  ./.venv/bin/python tasks/rewrite_existing_articles.py --dry-run

To actually overwrite files:
  ./.venv/bin/python tasks/rewrite_existing_articles.py

This script:
- Finds templates in app/templates/blog_*.html
- Extracts the <article class="blog-prose">...</article> block
- Sends content + title to the writer provider (OpenAI) to rewrite following the SEO checklist
- Scores the rewritten article using the site's scoring function and replaces the template if score >= threshold (or --force)
"""
from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
from typing import Tuple

import time


def _load_env(project_root: Path) -> None:
    env_path = project_root / ".env"
    if not env_path.exists():
        return
    try:
        from dotenv import load_dotenv  # type: ignore

        load_dotenv(env_path)
    except Exception:
        pass


def score_article(html: str, title: str, description: str, threshold_keyword: str | None = None) -> Tuple[int, dict]:
    breakdown: dict[str, int] = {}
    total = 0

    words = len(re.findall(r"\w+", re.sub(r"<[^>]+>", " ", html)))
    wc_pts = min(15, int(15 * min(1.0, words / 700)))
    breakdown["word_count"] = wc_pts
    total += wc_pts

    tlen = len(title or "")
    title_pts = 10 if 40 <= tlen <= 70 else (5 if 30 <= tlen < 40 or 70 < tlen <= 80 else 0)
    breakdown["title_length"] = title_pts
    total += title_pts

    dlen = len(description or "")
    meta_pts = 10 if 120 <= dlen <= 160 else (5 if 100 <= dlen < 120 or 160 < dlen <= 180 else 0)
    breakdown["meta_description"] = meta_pts
    total += meta_pts

    h2_count = len(re.findall(r"<h2\b", html, flags=re.I))
    h2_pts = 10 if h2_count >= 3 else (5 if h2_count == 2 else 0)
    breakdown["h2_count"] = h2_pts
    total += h2_pts

    kw = (threshold_keyword or "").strip().lower()
    first_para = ""
    m = re.search(r"<p\b[^>]*>(.*?)</p>", html, flags=re.I | re.S)
    if m:
        first_para = re.sub(r"<[^>]+>", "", m.group(1) or "").strip().lower()
    title_has = kw and kw in (title or "").lower()
    para_has = kw and kw in first_para
    kw_pts = 0
    if kw:
        if title_has and para_has:
            kw_pts = 10
        elif title_has or para_has:
            kw_pts = 5
    else:
        kw_pts = 5 if title else 0
    breakdown["keyword_presence"] = kw_pts
    total += kw_pts

    internal_links = re.findall(r'href=["\'](/[^"\']+)["\']', html)
    int_pts = 10 if len(internal_links) >= 1 else 0
    breakdown["internal_links"] = int_pts
    total += int_pts

    external_links = re.findall(r'href=["\']https?://([^"\']+)["\']', html)
    external_filtered = [u for u in external_links if "sparksmetrics" not in u.lower()]
    ext_pts = 5 if len(external_filtered) >= 1 else 0
    breakdown["external_links"] = ext_pts
    total += ext_pts

    img_tags = re.findall(r"<img\b[^>]*>", html, flags=re.I)
    img_with_alt = [t for t in img_tags if re.search(r'\balt=["\'].*?["\']', t, flags=re.I)]
    img_pts = 0
    if img_tags:
        img_pts = 5 if len(img_with_alt) == len(img_tags) else 2
    breakdown["images_alt"] = img_pts
    total += img_pts

    toc = 5 if re.search(r"(Table of contents|<nav[^>]+toc|id=[\"']toc[\"'])", html, flags=re.I) else 0
    breakdown["toc"] = toc
    total += toc

    ai_phrases = ["as an ai", "as an ai language model", "in this article we will", "in this post i"]
    ai_found = any(p in html.lower() for p in ai_phrases)
    ai_pts = 0 if ai_found else 5
    breakdown["ai_phrases"] = ai_pts
    total += ai_pts

    schema_pts = 5 if re.search(r"application/ld\+json", html, flags=re.I) else 0
    breakdown["schema"] = schema_pts
    total += schema_pts

    breakdown["mobile"] = 5
    total += 5

    author_found = bool(re.search(r'author|byline|class=["\']author', html, flags=re.I))
    references_found = bool(re.search(r"references|sources|cite", html, flags=re.I))
    trust_pts = 10 if author_found and references_found else (5 if author_found or references_found else 0)
    breakdown["trust_signals"] = trust_pts
    total += trust_pts

    score = min(100, int(total))
    return score, breakdown


def _call_openai_rewrite(title: str, existing_html: str) -> dict:
    """Call OpenAI Responses API to rewrite article following the SEO checklist.
    Returns dict with keys: title, description, html
    """
    api_key = (os.environ.get("OPENAI_API_KEY") or os.environ.get("OPEN_AI_KEY") or "").strip()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY or OPEN_AI_KEY not set in env.")
    base = (os.environ.get("OPENAI_BASE_URL") or "https://api.openai.com/v1").rstrip("/")
    model = (os.environ.get("OPENAI_MODEL") or "gpt-4.1-mini").strip()

    system = (
        "You are an expert SEO editor. Rewrite the provided HTML article to follow this checklist:\n"
        "- Target one primary keyword (use the one in the current title)\n"
        "- Satisfy dominant intent and cover the topic thoroughly\n"
        "- Clear H1, H2/H3 structure, short paragraphs, bullets where helpful\n"
        "- Title tag optimized for CTR, meta description <=160 chars\n"
        "- Include at least one internal link to /schedule-a-call/ and one external authoritative link\n"
        "- Ensure images have alt text (if images present) and add a small author byline\n"
        "- Add schema.org Article JSON-LD at the top if appropriate\n        "
        "Output strictly as JSON with keys: title, description, html (html is an HTML fragment suitable for insertion inside <article class=\"blog-prose\">).</n"
    )

    prompt = f"""Rewrite the article below. Preserve factual content and examples. Improve clarity, add structure (h2/h3), add CTAs and internal/external links, and ensure it meets SEO checklist. Do NOT include <article> wrapper — only the inner HTML.

Current title: {title}

Article HTML:
{existing_html[:12000]}
"""
    try:
        import requests  # type: ignore
    except Exception:
        # Fallback: naive rewrite (no external API). Try to improve structure slightly.
        desc = re.sub(r"<[^>]+>", " ", existing_html)
        desc = re.sub(r"\s+", " ", desc).strip()[:157]
        if len(desc) > 150:
            desc = desc[:157] + "..."
        # Ensure an author byline and internal CTA exist
        author = '<p class="byline">By Sparksmetrics — CRO & Analytics</p>'
        if "<p class=\"byline\">" not in existing_html:
            new_html = author + "\n" + existing_html
        else:
            new_html = existing_html
        # add internal CTA at the end if missing
        if "/schedule-a-call/" not in new_html:
            new_html = new_html + '\n<div class="callout"><p class="callout-title">Want help?</p><a class="btn btn-primary" href="/schedule-a-call/">Hire Sparksmetrics</a></div>'
        # Add simple JSON-LD Article schema
        schema = {
            "@context": "https://schema.org",
            "@type": "Article",
            "headline": title,
            "author": {"@type": "Person", "name": "Sparksmetrics"},
        }
        schema_html = f'<script type="application/ld+json">{json.dumps(schema)}</script>\n'
        final_html = schema_html + new_html
        return {"title": title, "description": desc, "html": final_html}

    resp = requests.post(
        f"{base}/responses",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "model": model,
            "input": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "text": {"format": {"type": "json_object"}},
        },
        timeout=60,
    )
    resp.raise_for_status()
    data = resp.json()
    out = (data.get("output_text") or "").strip()
    try:
        obj = json.loads(out)
    except Exception:
        return {"title": title, "description": "", "html": out}
    return obj


def extract_article_block(template_text: str) -> Tuple[str, Tuple[int, int]]:
    """Return inner HTML of <article class containing blog-prose>...</article> and (start,end) indices."""
    m = re.search(r'(<article[^>]*class=["\'][^"\']*blog-prose[^"\']*["\'][^>]*>)(.*?)(</article>)', template_text, flags=re.I | re.S)
    if not m:
        raise RuntimeError("No <article class containing \"blog-prose\"> block found")
    inner = m.group(2)
    start = m.start(2)
    end = m.end(2)
    return inner, (start, end)


def run(dry_run: bool = True, force: bool = False, threshold: int = 70):
    project_root = Path(__file__).resolve().parents[1]
    _load_env(project_root)
    templates_dir = project_root / "app" / "templates"
    files = sorted(templates_dir.glob("blog_*.html"))
    if not files:
        print("No blog templates found.")
        return
    for f in files:
        txt = f.read_text(encoding="utf-8")
        # Extract title from template (Jinja uses {{ post.title }}) — try to find h1 content or placeholder
        mtitle = re.search(r"<h1[^>]*>(.*?)</h1>", txt, flags=re.I | re.S)
        title = mtitle.group(1).strip() if mtitle else f.stem
        try:
            inner, (s, e) = extract_article_block(txt)
        except Exception as exc:
            print(f"Skipping {f.name}: {exc}")
            continue

        print(f"Processing {f.name} — title: {title}")
        try:
            rewritten = _call_openai_rewrite(title=title, existing_html=inner)
        except Exception as exc:
            print(f"Rewrite failed for {f.name}: {exc}")
            continue

        new_html = rewritten.get("html") or ""
        new_title = rewritten.get("title") or title
        new_description = rewritten.get("description") or ""

        score, breakdown = score_article(new_html, new_title, new_description, threshold_keyword=None)
        print(f"SEO score for {f.name}: {score} — breakdown: {breakdown}")

        if score < threshold and not force:
            print(f"Skipping overwrite for {f.name} (score {score} < {threshold}). Use --force to override.")
            continue

        # Build new template text: replace inner article block and update title/description placeholders if present
        new_txt = txt[:s] + "\n" + new_html.strip() + "\n" + txt[e:]
        # Replace static title occurrences if template hardcodes title (best-effort)
        new_txt = re.sub(r'(<h1[^>]*>)(.*?)(</h1>)', r'\1' + new_title + r'\3', new_txt, count=1, flags=re.I | re.S)
        # Replace meta description blocks (if template sets meta via block meta_description using post.description, skip)
        if dry_run:
            print(f"[dry-run] Would overwrite {f.name} with new HTML (score {score}).")
        else:
            f.write_text(new_txt, encoding="utf-8")
            print(f"Wrote updated template: {f.name}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Don't write files")
    parser.add_argument("--force", action="store_true", help="Overwrite even if score below threshold")
    parser.add_argument("--threshold", type=int, default=70, help="Publish threshold (0-100)")
    args = parser.parse_args()
    run(dry_run=args.dry_run, force=args.force, threshold=args.threshold)

