"""
Simple publisher: create a blog post from a raw transcript text.

Usage:
  ./.venv/bin/python tasks/simple_publish_from_transcript.py --slug 5-cro-mistakes-ecommerce-brands-make --transcript-file tasks/_transcript.txt
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from pathlib import Path as _Path
import sys as _sys

# Ensure package import works when running as script
_root = _Path(__file__).resolve().parents[1]
if str(_root) not in _sys.path:
    _sys.path.insert(0, str(_root))

from tasks.auto_blog_from_youtube import _load_env, build_post_template, slugify


def load_transcript(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip()


def split_into_sections(transcript: str, n: int = 5) -> list[str]:
    # naive split by sentences into roughly n chunks
    sentences = re.split(r"(?<=[.!?])\s+", transcript)
    if not sentences:
        return []
    chunk_size = max(1, len(sentences) // n)
    sections = []
    for i in range(0, len(sentences), chunk_size):
        sec = " ".join(sentences[i : i + chunk_size]).strip()
        if sec:
            sections.append(sec)
    return sections[:n]


def paragraphs_from_text(text: str) -> list[str]:
    paras = [p.strip() for p in re.split(r"\n{1,}|\r\n{1,}", text) if p.strip()]
    if not paras:
        # fallback: split by sentences into paragraphs of ~3 sentences
        sents = re.split(r"(?<=[.!?])\s+", text)
        paras = []
        for i in range(0, len(sents), 3):
            paras.append(" ".join(sents[i : i + 3]).strip())
    return paras


def build_article_html_from_transcript(transcript: str) -> str:
    paras = paragraphs_from_text(transcript)
    sections = split_into_sections(transcript, n=5)
    parts = []
    parts.append('<nav id="toc" class="mb-6 p-4 bg-primary/5 rounded-lg"><strong>Table of contents</strong><ul class="ml-4 mt-2">')
    for i, s in enumerate(sections, 1):
        parts.append(f'<li><a href="#sec-{i}">Section {i}</a></li>')
    parts.append("</ul></nav>")

    # intro
    if paras:
        parts.append(f"<p>{paras[0]}</p>")

    # sections
    for i, s in enumerate(sections, 1):
        parts.append(f'<h2 id="sec-{i}">Section {i}</h2>')
        parts.append(f"<p>{s}</p>")

    # checklist: top actionable bullets extracted naively from transcript (first lines with verbs)
    checklist = []
    for p in paras[:8]:
        m = re.match(r"^(?:You should|You can|Make sure|Run|Use|Ask)\b.*", p, flags=re.I)
        if m:
            checklist.append(p if len(p) < 220 else p[:217] + "...")
    if not checklist:
        checklist = [
            "Run qualitative research (surveys, recordings, interviews)",
            "Segment funnels by device and traffic source",
            "Prioritize tests using ICE or RICE",
        ]

    parts.append('<section class="mt-10 p-6 bg-light-base border border-gray-200 rounded-2xl">')
    parts.append("<h3>Implementation checklist</h3><ul>")
    for it in checklist:
        parts.append(f"<li>{it}</li>")
    parts.append("</ul></section>")

    # FAQs simple
    parts.append("<section class='mt-8'><h3>FAQs</h3>")
    parts.append("<h4>How long will this take?</h4><p>Small wins can appear within weeks; larger programs require months.</p>")
    parts.append("<h4>Do I need developer help?</h4><p>Some tests are low-effort; others need dev resources.</p></section>")

    return "\n".join(parts)


def run(slug: str, transcript_file: Path, overwrite: bool = True):
    project_root = Path(__file__).resolve().parents[1]
    _load_env(project_root)
    templates_dir = project_root / "app" / "templates"
    posts_path = project_root / "app" / "blog_posts.json"

    tpl_name = f"blog_{slug}.html"
    tpl_path = templates_dir / tpl_name

    post_meta = {}
    if posts_path.exists():
        data = json.loads(posts_path.read_text(encoding="utf-8"))
        posts = data.get("posts") if isinstance(data, dict) else data
        post_meta = next((p for p in posts if p.get("slug") == slug), {}) if posts else {}

    transcript = load_transcript(transcript_file)
    article_html = build_article_html_from_transcript(transcript)

    title = post_meta.get("title") or slug.replace("-", " ").title()
    description = post_meta.get("description") or (transcript[:157] + "..." if len(transcript) > 160 else transcript)
    post = {
        "slug": slug,
        "title": title,
        "description": description,
        "published_date": post_meta.get("published_date") or post_meta.get("updated_date") or "11 Feb 2026",
        "updated_date": post_meta.get("updated_date") or post_meta.get("published_date") or "11 Feb 2026",
        "reading_time": post_meta.get("reading_time") or "8 min read",
        "category": post_meta.get("category") or "CRO",
        "template": tpl_name,
        "video_id": post_meta.get("video_id") or "",
    }

    template_text = build_post_template(video_id=post["video_id"], post=post, article_html=article_html)
    if overwrite:
        tpl_path.write_text(template_text, encoding="utf-8")
        print("Wrote template:", tpl_path)
        # update posts JSON
        posts = []
        if posts_path.exists():
            data = json.loads(posts_path.read_text(encoding="utf-8"))
            posts = data.get("posts") if isinstance(data, dict) else data
            # remove existing with same slug
            posts = [p for p in posts if p.get("slug") != slug]
        posts.insert(0, post)
        posts_path.write_text(json.dumps({"posts": posts}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print("Updated posts json:", posts_path)
    else:
        print("[dry-run] Would write template:", tpl_path)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--slug", required=True)
    parser.add_argument("--transcript-file", required=True)
    parser.add_argument("--no-overwrite", action="store_true")
    args = parser.parse_args()
    run(args.slug, Path(args.transcript_file), overwrite=not args.no_overwrite)

