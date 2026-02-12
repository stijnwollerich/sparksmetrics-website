"""
Expand a single existing blog article to at least 1000 words using the OpenAI Responses API.

Requirements:
- Set OPENAI_API_KEY or OPEN_AI_KEY in .env
- This script uses urllib so it doesn't need 'requests'.

Usage:
  ./.venv/bin/python tasks/llm_expand_article.py --slug cro-audit-that-finds-real-leaks --dry-run
  ./.venv/bin/python tasks/llm_expand_article.py --slug cro-audit-that-finds-real-leaks
"""
from __future__ import annotations

import argparse
import json
import os
import re
import ssl
import urllib.request
from pathlib import Path
from typing import Optional


def load_env(root: Path) -> None:
    env = root / ".env"
    if not env.exists():
        return
    try:
        from dotenv import load_dotenv  # type: ignore

        load_dotenv(env)
    except Exception:
        for line in env.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def extract_article_block(template_text: str) -> tuple[str, int, int]:
    m = re.search(r'(<article[^>]*class=["\'][^"\']*blog-prose[^"\']*["\'][^>]*>)(.*?)(</article>)', template_text, flags=re.I | re.S)
    if not m:
        raise RuntimeError("No blog article block found")
    return m.group(2), m.start(2), m.end(2)


def build_prompt(title: str, existing_html: str) -> str:
    return f"""
You are an expert SEO writer and editor for a CRO/analytics agency.
Rewrite and expand the article to be a high-quality blog post of at least 1000 words,
formatted as HTML fragment suitable for insertion inside <article class="blog-prose">.

Requirements:
- Use the title: {title}
- Target commercial/informational CRO intent.
- Include clear H2 and H3 headings, short paragraphs, bullets/lists where helpful.
- Add real, practical examples, checklists, and an implementation section.
- Include at least one internal CTA linking to /schedule-a-call/ and one CTA to download the ebook.
- Output only a JSON object with keys: title, description (<=160 chars), html
- The html value must be the HTML fragment (no <article> wrapper). Ensure image alts if images included.
- Avoid generic AI disclaimers. Be authoritative and specific.

Existing article HTML (for reference): {existing_html[:8000]}
"""


def call_openai(prompt: str, model: str, api_key: str, timeout: int = 120) -> dict:
    base = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    url = f"{base}/responses"
    payload = {
        "model": model,
        "input": [
            {"role": "system", "content": "You are a helpful SEO writing assistant."},
            {"role": "user", "content": prompt},
        ],
        "text": {"format": {"type": "json_object"}},
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}, method="POST")
    ctx = ssl.create_default_context()
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
        return json.load(resp)


def parse_response(resp: dict) -> Optional[dict]:
    # Try common shapes
    if not isinstance(resp, dict):
        return None
    if "output_text" in resp and resp["output_text"]:
        try:
            return json.loads(resp["output_text"])
        except Exception:
            return {"title": None, "description": None, "html": resp["output_text"]}
    out = resp.get("output") or resp.get("choices") or []
    # Try to find content in output
    texts = []
    for item in out:
        if isinstance(item, dict):
            contents = item.get("content") or item.get("message") or []
            if isinstance(contents, list):
                for c in contents:
                    if isinstance(c, dict) and c.get("type") in ("output_text", "output", "message"):
                        txt = c.get("text") or c.get("content") or ""
                        texts.append(txt)
            else:
                txt = item.get("text") or item.get("message") or ""
                if txt:
                    texts.append(txt)
    joined = "\n".join(texts).strip()
    if not joined:
        return None
    try:
        return json.loads(joined)
    except Exception:
        return {"title": None, "description": None, "html": joined}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--slug", required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--model", default=os.environ.get("OPENAI_MODEL", "gpt-4.1-mini"))
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parents[1]
    load_env(project_root)
    api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("OPEN_AI_KEY")
    if not api_key:
        raise SystemExit("OPENAI_API_KEY or OPEN_AI_KEY not set in .env")

    templates_dir = project_root / "app" / "templates"
    # Support slug with hyphens or underscores
    candidate1 = templates_dir / f"blog_{args.slug}.html"
    candidate2 = templates_dir / f"blog_{args.slug.replace('-', '_')}.html"
    tpl = candidate1 if candidate1.exists() else (candidate2 if candidate2.exists() else candidate1)
    if not tpl.exists():
        raise SystemExit(f"Template not found: {tpl}")
    txt = tpl.read_text(encoding="utf-8")
    inner, s, e = extract_article_block(txt)
    title_m = re.search(r"<h1[^>]*>(.*?)</h1>", txt, flags=re.I | re.S)
    title = title_m.group(1).strip() if title_m else args.slug
    prompt = build_prompt(title, inner)
    resp = call_openai(prompt, args.model, api_key)
    parsed = parse_response(resp)
    if not parsed or not parsed.get("html"):
        raise SystemExit("Failed to parse OpenAI response")
    new_html = parsed["html"]
    # Ensure description
    description = parsed.get("description") or (inner.strip()[:157] + "...")
    new_txt = txt[:s] + "\n" + new_html.strip() + "\n" + txt[e:]
    # Replace meta description block if present: look for block/meta in head — skip to be safe
    if args.dry_run:
        print(f"[dry-run] would overwrite {tpl}")
    else:
        tpl.write_text(new_txt, encoding="utf-8")
        print(f"Wrote {tpl}")


if __name__ == "__main__":
    main()

