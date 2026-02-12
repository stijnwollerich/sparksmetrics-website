"""
Deterministically expand a transcript into multi-paragraph sections (no LLM).
Overwrites the post template with fuller paragraphs.

Usage:
  ./.venv/bin/python tasks/force_paragraph_expand.py --slug 5-cro-mistakes-ecommerce-brands-make --transcript-file tasks/_transcript_qed0zrqFYeg.txt
"""
from __future__ import annotations

import argparse
import math
import re
from pathlib import Path
from pathlib import Path as _Path
import sys as _sys

# Ensure imports path
_root = _Path(__file__).resolve().parents[1]
if str(_root) not in _sys.path:
    _sys.path.insert(0, str(_root))

from tasks.auto_blog_from_youtube import _load_env, build_post_template


def sentences(text: str) -> list[str]:
    s = re.split(r'(?<=[.!?])\s+', text.strip())
    return [seg.strip() for seg in s if seg.strip()]


def build_paragraphs_from_sentences(sents: list[str], target_words: int) -> list[str]:
    paras = []
    cur = []
    cur_words = 0
    for sent in sents:
        w = len(re.findall(r"\w+", sent))
        cur.append(sent)
        cur_words += w
        if cur_words >= 120:  # ~120 words per paragraph
            paras.append(" ".join(cur))
            cur = []
            cur_words = 0
    if cur:
        paras.append(" ".join(cur))
    # trim or extend to reach approximate target_words by number of paragraphs
    if not paras:
        return [ " ".join(sents) ]
    return paras


def run(slug: str, transcript_file: Path, overwrite: bool = True, target_words: int = 1200):
    project_root = Path(__file__).resolve().parents[1]
    _load_env(project_root)
    tpl_name = f"blog_{slug}.html"
    templates_dir = project_root / "app" / "templates"
    tpl_path = templates_dir / tpl_name

    text = transcript_file.read_text(encoding="utf-8")
    sents = sentences(text)
    if not sents:
        raise SystemExit("Transcript has no sentences.")

    # create 5 sections
    num_sections = 5
    per_section = max(1, len(sents) // num_sections)
    sections = []
    for i in range(num_sections):
        chunk = sents[i * per_section : (i + 1) * per_section]
        if not chunk:
            continue
        paras = build_paragraphs_from_sentences(chunk, target_words // num_sections)
        sections.append({"h2": f"Section {i+1}", "paragraphs": paras})

    # assemble HTML
    parts = []
    parts.append('<nav id="toc" class="mb-6 p-4 bg-primary/5 rounded-lg"><strong>Table of contents</strong><ul class="ml-4 mt-2">')
    for i, sec in enumerate(sections, 1):
        parts.append(f'<li><a href="#sec-{i}">{sec["h2"]}</a></li>')
    parts.append("</ul></nav>")

    for i, sec in enumerate(sections, 1):
        parts.append(f'<h2 id="sec-{i}">{sec["h2"]}</h2>')
        for p in sec["paragraphs"]:
            parts.append(f"<p>{p}</p>")
        # add a tip banner occasionally
        if i % 2 == 0:
            parts.append(f'<div class="tip-banner"><strong>Tip:</strong> Focus research on high-intent pages for fastest wins.</div>')

    parts.append('<section class="mt-10 p-6 bg-light-base border border-gray-200 rounded-2xl"><h3>Implementation checklist</h3><ul>')
    parts += [ "<li>Run qualitative research (surveys, recordings, interviews)</li>", "<li>Segment funnels by device and channel</li>", "<li>Prioritize tests using ICE or RICE</li>", "<li>Optimize copy: headlines, CTAs, guarantees</li>" ]
    parts.append("</ul></section>")

    parts.append("<section class='mt-8'><h3>FAQs</h3><h4>How long will this take?</h4><p>Small wins can appear within weeks; larger programs require months.</p><h4>Do I need developer help?</h4><p>Some tests are low-effort; others need dev resources.</p></section>")

    article_html = "\n".join(parts)

    # Build post metadata (simple)
    post = {
        "slug": slug,
        "title": slug.replace("-", " ").title(),
        "description": (text[:157] + "...") if len(text) > 160 else text,
        "published_date": "11 Feb 2026",
        "updated_date": "11 Feb 2026",
        "reading_time": f"{max(4, target_words//200)} min read",
        "category": "CRO",
        "template": tpl_name,
        "video_id": "",
    }

    template_text = build_post_template(video_id=post.get("video_id") or "", post=post, article_html=article_html)
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

