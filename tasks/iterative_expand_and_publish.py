"""
Iterative transcript expansion:
- split transcript into chunks
- for each chunk: try OpenAI expansion (section HTML)
- fallback to deterministic paragraph expansion when OpenAI fails
- assemble structured spec and render into styled template (overwrite)

Usage:
  ./.venv/bin/python tasks/iterative_expand_and_publish.py --slug 5-cro-mistakes-ecommerce-brands-make --transcript-file tasks/_transcript_qed0zrqFYeg.txt
"""
from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path
from pathlib import Path as _Path
import sys as _sys
import time

# Ensure imports
_root = _Path(__file__).resolve().parents[1]
if str(_root) not in _sys.path:
    _sys.path.insert(0, str(_root))

from tasks.auto_blog_from_youtube import _load_env, expand_article_with_openai, build_post_template


def split_transcript_into_chunks(transcript: str, n_chunks: int = 5) -> list[str]:
    # split by paragraphs roughly into n_chunks
    paras = [p.strip() for p in re.split(r"\n{1,}|\r\n{1,}", transcript) if p.strip()]
    if not paras:
        # fallback: split by sentences
        paras = re.split(r"(?<=[.!?])\s+", transcript)
    total = len(paras)
    if total == 0:
        return []
    chunk_size = max(1, math.ceil(total / n_chunks))
    chunks = []
    for i in range(0, total, chunk_size):
        chunks.append(" ".join(paras[i : i + chunk_size]).strip())
    return chunks[:n_chunks]


def deterministic_expand_chunk(chunk: str) -> str:
    # create 2-4 paragraphs from chunk by sentence grouping
    sents = [s.strip() for s in re.split(r"(?<=[.!?])\s+", chunk) if s.strip()]
    if not sents:
        return f"<p>{chunk}</p>"
    per_para = max(1, math.ceil(len(sents) / 3))
    paras = []
    for i in range(0, len(sents), per_para):
        paras.append(" ".join(sents[i : i + per_para]))
    return "\n".join(f"<p>{p}</p>" for p in paras)


def try_expand_with_openai(title: str, chunk: str, model: str = "gpt-4.1-mini") -> str | None:
    # Try expand_article_with_openai (returns dict with html), with retries
    api_retries = 2
    for attempt in range(api_retries):
        try:
            out = expand_article_with_openai(title=title, transcript=chunk, existing_html="", model=model)
            if isinstance(out, dict) and out.get("html"):
                return out.get("html")
        except Exception:
            time.sleep(1 + attempt * 2)
    return None


def assemble_full_html(title: str, description: str, sections_html: list[str]) -> str:
    parts = []
    # hero
    parts.append(f'<div class="article-hero"><div class="kicker">CRO</div><h2>{title}</h2><p class="lead">{description}</p><div class="mt-6 flex gap-3"><a class="btn btn-primary" href="/schedule-a-call/">Hire Sparksmetrics</a><button class="btn btn-outline" data-checklist-modal>Download free ebook</button><button class="btn btn-soft" data-audit-modal>Claim free CRO audit</button></div></div>')
    # toc
    parts.append('<nav id="toc" class="mb-6 p-4 bg-primary/5 rounded-lg"><strong>Table of contents</strong><ul class="ml-4 mt-2">')
    for i in range(len(sections_html)):
        parts.append(f'<li><a href="#sec-{i+1}">Section {i+1}</a></li>')
    parts.append("</ul></nav>")
    # sections
    for i, html in enumerate(sections_html, 1):
        parts.append(f'<h2 id="sec-{i}">Section {i}</h2>')
        parts.append(html)
        if i % 2 == 0:
            parts.append('<div class="tip-banner"><strong>Tip:</strong> Prioritise tests by impact and ease to keep momentum.</div>')
    # checklist + faqs
    parts.append('<section class="mt-10 p-6 bg-light-base border border-gray-200 rounded-2xl"><h3>Implementation checklist</h3><ul><li>Run qualitative research (surveys/recordings/interviews)</li><li>Segment funnels by device and channel</li><li>Prioritize tests using ICE or RICE</li><li>Optimize copy: headlines, CTAs</li></ul></section>')
    parts.append("<section class='mt-8'><h3>FAQs</h3><h4>How long will this take?</h4><p>Small wins can appear in weeks; programmatic CRO requires months.</p><h4>Do I need developer help?</h4><p>Some tests are low-effort; large changes need dev resources.</p></section>")
    return "\n".join(parts)


def run(slug: str, transcript_file: Path, overwrite: bool = True):
    project_root = Path(__file__).resolve().parents[1]
    _load_env(project_root)
    transcript = transcript_file.read_text(encoding="utf-8")
    title = "5 CRO mistakes 90+ e-commerce brands make (and how to fix them)"
    description = "Practical CRO research, prioritization, copy and testing guidance from a 90+ ecommerce study."

    chunks = split_transcript_into_chunks(transcript, n_chunks=5)
    sections_html = []
    for chunk in chunks:
        html = try_expand_with_openai(title=title, chunk=chunk)
        if html:
            # ensure paragraphs wrap
            if not re.search(r"<p\b", html):
                html = "<p>" + html.replace("\n", " ") + "</p>"
            sections_html.append(html)
        else:
            sections_html.append(deterministic_expand_chunk(chunk))

    full_html = assemble_full_html(title, description, sections_html)

    post = {
        "slug": slug,
        "title": title,
        "description": description,
        "published_date": "11 Feb 2026",
        "updated_date": "11 Feb 2026",
        "reading_time": "10 min read",
        "category": "CRO",
        "template": f"blog_{slug}.html",
        "video_id": "",
    }

    template_text = build_post_template(video_id=post["video_id"], post=post, article_html=full_html)
    tpl_path = project_root / "app" / "templates" / post["template"]
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

