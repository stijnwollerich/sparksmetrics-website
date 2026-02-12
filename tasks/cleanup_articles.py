"""
Cleanup blog templates after deterministic enrichment.

This script:
- Removes duplicated injected snippets (the "Why this matters" block) that were accidentally inserted into paragraphs.
- Ensures a single clean "why/how/checklist" block exists after each <h2>.
- Repairs a few common malformed tag artifacts introduced by naive regex operations.
"""
from __future__ import annotations

import re
from pathlib import Path


INJECT_SNIPPET_PATTERN = re.compile(
    r'(<p><strong>Why this matters</strong>.*?<ul>.*?</ul></p>)',
    flags=re.I | re.S,
)

def clean_inner(inner: str) -> str:
    # Aggressively remove injected "Why this matters" blocks in several forms
    inner = re.sub(r'<p>\s*<strong>\s*Why this matters\s*</strong>.*?</ul>\s*</p>', '', inner, flags=re.I | re.S)
    inner = re.sub(r'<p>\s*<strong>\s*Why this matters\s*</strong>.*?</p>', '', inner, flags=re.I | re.S)
    inner = re.sub(r'<p>\s*How to check:.*?</ul>\s*</p>', '', inner, flags=re.I | re.S)
    inner = INJECT_SNIPPET_PATTERN.sub("", inner)
    # Remove any standalone "How to check:" followed by lists without enclosing closing p tags
    inner = re.sub(r'How to check:.*?</ul>', '', inner, flags=re.I | re.S)
    # Remove orphaned duplicated quick-test lists (two or more repeated identical ul blocks) — collapse to single
    inner = re.sub(r'(<ul>\s*<li>Quick test 1:.*?</li>\s*<li>Quick test 2:.*?</li>\s*<li>Quick test 3:.*?</li>\s*</ul>)(\s*\1)+', r'\1', inner, flags=re.I | re.S)
    # Remove accidental multiple insertions of the same checklist text anywhere
    inner = re.sub(r'(<p>\s*<strong>\s*Why this matters.*?</ul>\s*</p>)+', '', inner, flags=re.I | re.S)

    # Remove stray broken tokens like "</o" or "<o" left from truncation
    inner = re.sub(r"</?o\b[^>]*>", "", inner)

    # Normalize multiple blank lines
    inner = re.sub(r"\n\s*\n\s*\n+", "\n\n", inner)

    # For each H2, ensure the clean snippet is present once after the H2 if there are less than 2 paragraphs following
    def ensure_block(match):
        h2 = match.group(0)
        # Look ahead a little to see if there are two <p> after
        rest = match.string[match.end(): match.end() + 400]
        paras = re.findall(r"<p\b", rest, flags=re.I)
        if len(paras) >= 2:
            return h2
        block = (
            '<p><strong>Why this matters</strong> — brief explanation of the importance and impact for ecommerce teams.</p>'
            '<p>How to check: run the quick tests and look for the signs described above. Use segmentation (mobile vs desktop) and session recordings where useful.</p>'
            '<ul><li>Quick test 1: reproduce the funnel step and log the dropoff.</li>'
            '<li>Quick test 2: add a short survey to capture user hesitation.</li>'
            '<li>Quick test 3: run a small A/B experiment for the proposed fix.</li></ul>'
        )
        return h2 + "\n" + block

    inner = re.sub(r"<h2\b[^>]*>.*?</h2>", ensure_block, inner, flags=re.I | re.S)

    # Fix malformed list/ol fragments like "</o" or "l>" leftover
    inner = inner.replace("</o", "").replace("l>", "l>")

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
        new_inner = clean_inner(inner)
        new_txt = before + new_inner + after
        f.write_text(new_txt, encoding="utf-8")
        print(f"Cleaned {f.name}")


if __name__ == "__main__":
    run()

