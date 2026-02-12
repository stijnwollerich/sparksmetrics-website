"""
Deterministically enrich existing blog articles when an LLM is not available.

This script:
- Finds templates app/templates/blog_*.html
- Adds a Table of Contents if missing
- For each H2, ensures there are at least 2 paragraphs and a 3-item checklist after it.
- Adds an "Implementation checklist" near the end if missing.
"""
from __future__ import annotations

import re
from pathlib import Path


def ensure_toc(html: str) -> str:
    if re.search(r"(Table of contents|<nav[^>]+toc|id=[\"']toc[\"'])", html, flags=re.I):
        return html
    # Build TOC from H2 headings
    headers = re.findall(r"<h2[^>]*>(.*?)</h2>", html, flags=re.I | re.S)
    if not headers:
        return html
    toc_items = []
    for i, h in enumerate(headers, 1):
        text = re.sub(r"<[^>]+>", "", h).strip()
        anchor = f"toc-{i}"
        toc_items.append(f'<li><a href="#{anchor}">{text}</a></li>')
        # add id to header
        html = html.replace(h, f'{h}<span id="{anchor}"></span>', 1)
    toc_html = "<nav id=\"toc\" class=\"mb-6 p-4 bg-primary/5 rounded-lg\"><strong>Table of contents</strong><ul class=\"ml-4 mt-2\">"
    toc_html += "\n".join(toc_items)
    toc_html += "</ul></nav>\n"
    # Insert TOC after first <p> or at top
    m = re.search(r"(<p\b[^>]*>.*?</p>)", html, flags=re.I | re.S)
    if m:
        return html.replace(m.group(1), m.group(1) + "\n" + toc_html, 1)
    return toc_html + html


def expand_h2_sections(html: str) -> str:
    def repl(match):
        h2 = match.group(0)
        content_after = match.group(1) or ""
        # If there are already 2 paragraphs right after, skip
        paras = re.findall(r"^\s*<p\b", content_after, flags=re.I)
        if len(paras) >= 2:
            return h2
        # Build extra content
        extra = (
            "<p><strong>Why this matters</strong> — brief explanation of the importance and impact for ecommerce teams.</p>"
            "<p>How to check: run the quick tests and look for the signs described above. Use segmentation (mobile vs desktop) and session recordings where useful.</p>"
            "<ul><li>Quick test 1: reproduce the funnel step and log the dropoff.</li><li>Quick test 2: add a short survey to capture user hesitation.</li><li>Quick test 3: run a small A/B experiment for the proposed fix.</li></ul>"
        )
        return h2 + "\n" + extra

    # Find each H2 and ensure content expanded
    pattern = re.compile(r"<h2\b[^>]*>.*?</h2>([\s\S]{0,400})", flags=re.I)
    new_html = pattern.sub(repl, html)
    return new_html


def ensure_implementation_checklist(html: str) -> str:
    if "Implementation checklist" in html:
        return html
    checklist = (
        "<section class=\"mt-10 p-6 bg-light-base border border-gray-200 rounded-2xl\">"
        "<h3>Implementation checklist</h3>"
        "<ul><li>Run qualitative research: surveys & recordings</li><li>Validate tracking & events</li><li>Prioritize using an objective framework</li><li>Run tests and record results</li></ul>"
        "</section>"
    )
    # Append before closing article if present
    if "</article>" in html:
        return html.replace("</article>", checklist + "</article>", 1)
    return html + checklist


def run():
    templates_dir = Path(__file__).resolve().parents[1] / "app" / "templates"
    files = sorted(templates_dir.glob("blog_*.html"))
    for f in files:
        txt = f.read_text(encoding="utf-8")
        m = re.search(r'(<article[^>]*class=["\'][^"\']*blog-prose[^"\']*["\'][^>]*>)(.*?)(</article>)', txt, flags=re.I | re.S)
        if not m:
            print(f"Skipping {f.name}: no article block")
            continue
        before, inner, after = txt[: m.start(2)], m.group(2), txt[m.end(2) :]
        new_inner = inner
        new_inner = ensure_toc(new_inner)
        new_inner = expand_h2_sections(new_inner)
        new_inner = ensure_implementation_checklist(new_inner)
        new_txt = before + new_inner + after
        f.write_text(new_txt, encoding="utf-8")
        print(f"Enriched {f.name}")


if __name__ == "__main__":
    run()

