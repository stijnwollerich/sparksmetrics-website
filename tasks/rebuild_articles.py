"""
Rebuild blog article inner HTML to remove malformed injections and produce clean structure.

This will:
- Extract h2 headings and the first clean paragraph after each h2.
- Build a Table of Contents.
- For each section, render h2 + paragraph + standardized why/how/checklist block.
- Preserve the Jinja placeholders like {{ post.title }} and {{ url_for(...) }}.
"""
from __future__ import annotations

import re
from pathlib import Path


def clean_text(s: str) -> str:
    s = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", s)).strip()
    return s


def extract_headings_and_paras(inner: str):
    # Find all h2 and capture following up to next h2
    parts = re.split(r"(<h2\b[^>]*>.*?</h2>)", inner, flags=re.I | re.S)
    headings = []
    # parts alternates: before, h2, content, h2, content...
    it = iter(parts)
    pre = next(it, "")
    for chunk in it:
        h2 = chunk
        content = next(it, "")
        # extract plain text h2
        h2_text = re.sub(r"<[^>]+>", "", h2).strip()
        # find first paragraph in content
        m = re.search(r"<p\b[^>]*>(.*?)</p>", content, flags=re.I | re.S)
        para = clean_text(m.group(1)) if m else ""
        headings.append((h2_text, para))
    return headings


def build_inner_from_sections(sections):
    # schema and byline
    inner = '<script type="application/ld+json">{"@context":"https://schema.org","@type":"Article","headline":"{{ post.title }}","author":{"@type":"Person","name":"Sparksmetrics"}}</script>\n'
    inner += '<p class="byline">By Sparksmetrics — CRO &amp; Analytics</p>\n'
    # TOC
    inner += '<nav id="toc" class="mb-6 p-4 bg-primary/5 rounded-lg"><strong>Table of contents</strong><ul class="ml-4 mt-2">\n'
    for i, (h, _) in enumerate(sections, 1):
        safe = h or f"Section {i}"
        inner += f'<li><a href="#toc-{i}">{safe}</a></li>\n'
    inner += "</ul></nav>\n\n"

    # sections
    for i, (h, p) in enumerate(sections, 1):
        safe_h = h or f"Section {i}"
        inner += f'<h2>{safe_h}<span id="toc-{i}"></span></h2>\n'
        if p:
            inner += f"<p>{p}</p>\n"
        else:
            inner += "<p>Summary: key takeaway and what to check.</p>\n"
        # standardized block
        block = (
            '<div class="callout"><p class="callout-title">Why this matters</p>'
            "<p>Brief explanation of the importance and impact for ecommerce teams.</p>"
            "<p>How to check: run quick tests and check segmentation (mobile vs desktop) and session recordings.</p>"
            "<ul><li>Quick test 1: reproduce the funnel step and log the dropoff.</li>"
            "<li>Quick test 2: add a short survey to capture user hesitation.</li>"
            "<li>Quick test 3: run a small A/B experiment for the proposed fix.</li></ul></div>\n"
        )
        inner += block
    # final CTA + checklist
    inner += (
        '<hr /><div class="callout"><p class="callout-title">Want us to run the audit?</p>'
        '<p>We’ll audit your funnel, implement fixes, and turn the findings into a prioritized test plan. '
        '<a href="{{ url_for(\'main.schedule_a_call\') }}">Book a call</a>.</p></div>\n'
    )
    inner += '<section class="mt-10 p-6 bg-light-base border border-gray-200 rounded-2xl"><h3>Implementation checklist</h3><ul>'
    inner += "<li>Run qualitative research: surveys & recordings</li>"
    inner += "<li>Validate tracking & events</li>"
    inner += "<li>Prioritize using an objective framework</li>"
    inner += "<li>Run tests and record results</li></ul></section>\n"
    return inner


def run():
    templates_dir = Path(__file__).resolve().parents[1] / "app" / "templates"
    for f in sorted(templates_dir.glob("blog_*.html")):
        txt = f.read_text(encoding="utf-8")
        m = re.search(r'(<article[^>]*class=["\'][^"\']*blog-prose[^"\']*["\'][^>]*>)(.*?)(</article>)', txt, flags=re.I | re.S)
        if not m:
            print(f"Skipping {f.name}: no article block")
            continue
        before, inner, after = txt[: m.start(2)], m.group(2), txt[m.end(2) :]
        sections = extract_headings_and_paras(inner)
        if not sections:
            print(f"Skipping {f.name}: no H2 headings found")
            continue
        new_inner = build_inner_from_sections(sections)
        new_txt = before + new_inner + after
        f.write_text(new_txt, encoding="utf-8")
        print(f"Rebuilt {f.name}")


if __name__ == "__main__":
    run()

