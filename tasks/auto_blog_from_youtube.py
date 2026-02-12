"""
Automated blog post generator for new YouTube uploads.

What it does:
- Polls a YouTube channel RSS feed for newest videos (no API key).
- Detects which videos already have blog posts (by video_id in app/blog_posts.json).
- Fetches transcript (requires captions) via youtube-transcript-api.
- Writes a new Jinja blog template in app/templates/ and appends metadata to app/blog_posts.json.
- Sends a Slack message when done (optional).

Cron example (every hour):
0 * * * * cd /path/to/sparksmetrics-website && ./.venv/bin/python tasks/auto_blog_from_youtube.py --channel UCkwylcLXJiV-kQxCZMRR-tw >> /var/log/sm_blog_cron.log 2>&1

Env vars (in sparksmetrics-website/.env):
- SLACK_WEBHOOK_URL=...
- SITE_BASE_URL=https://sparksmetrics.com
- OPENAI_API_KEY=... (optional; enables higher-quality writing)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import time
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import ssl
try:
    import requests  # type: ignore
except Exception:
    requests = None
# Hard-coded settings (non-secret)
BLOG_MIN_WORDS_DEFAULT = 1000
BLOG_PUBLISH_THRESHOLD_DEFAULT = 70
OPENAI_MODEL_DEFAULT = "gpt-4.1-mini"


def _load_env(project_root: Path) -> None:
    """Load .env if python-dotenv is installed; no-op otherwise."""
    env_path = project_root / ".env"
    if not env_path.exists():
        return
    try:
        from dotenv import load_dotenv  # type: ignore

        load_dotenv(env_path)
    except Exception:
        # Fallback: parse simple KEY=VALUE lines from .env into os.environ
        try:
            with env_path.open("r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if "=" not in line:
                        continue
                    key, val = line.split("=", 1)
                    key = key.strip()
                    val = val.strip().strip('"').strip("'")
                    # don't overwrite existing env vars
                    if key and not os.environ.get(key):
                        os.environ[key] = val
        except Exception:
            # Still ok: code reads os.environ and app/config.py also parses .env
            pass


def _http_get(url: str, timeout: int = 15) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "SparksmetricsBlogBot/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


@dataclass(frozen=True)
class YouTubeVideo:
    video_id: str
    title: str
    url: str
    published: str  # human string, e.g. "11 Feb 2026"


def fetch_latest_videos(channel_id: str, max_results: int = 5) -> list[YouTubeVideo]:
    """Fetch latest videos (id/title/url/published) from a channel RSS feed."""
    url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id.strip()}"
    raw = _http_get(url, timeout=15)

    root = ET.fromstring(raw)
    ns = {"atom": "http://www.w3.org/2005/Atom", "yt": "http://www.youtube.com/xml/schemas/2015"}
    videos: list[YouTubeVideo] = []
    for entry in root.findall("atom:entry", ns)[:max_results]:
        vid_el = entry.find("yt:videoId", ns)
        title_el = entry.find("atom:title", ns)
        link_el = entry.find("atom:link", ns)
        pub_el = entry.find("atom:published", ns)
        if vid_el is None or not (vid_el.text or "").strip():
            continue
        video_id = (vid_el.text or "").strip()
        title = (title_el.text or "").strip() if title_el is not None else video_id
        href = (link_el.get("href") or "").strip() if link_el is not None else f"https://youtu.be/{video_id}"

        published_raw = (pub_el.text or "").strip() if pub_el is not None else ""
        published_human = ""
        try:
            # Example: 2026-02-11T12:34:56+00:00
            dt = datetime.fromisoformat(published_raw.replace("Z", "+00:00"))
            published_human = dt.strftime("%d %b %Y").lstrip("0")
        except Exception:
            published_human = datetime.now(timezone.utc).strftime("%d %b %Y").lstrip("0")

        videos.append(YouTubeVideo(video_id=video_id, title=title, url=href, published=published_human))
    return videos


def slugify(text: str) -> str:
    text = text.strip().lower()
    text = text.replace("&", " and ")
    text = re.sub(r"[^a-z0-9\s-]", "", text)
    text = re.sub(r"\s+", "-", text).strip("-")
    text = re.sub(r"-{2,}", "-", text)
    return text[:80] or f"post-{int(time.time())}"


def estimate_reading_time(text: str, wpm: int = 200) -> str:
    words = len(re.findall(r"\w+", text))
    minutes = max(1, int(round(words / float(wpm))))
    return f"{minutes} min read"


def load_blog_posts(posts_path: Path) -> list[dict[str, Any]]:
    if not posts_path.exists():
        return []
    data = json.loads(posts_path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        return list(data.get("posts") or [])
    return list(data or [])


def save_blog_posts(posts_path: Path, posts: list[dict[str, Any]]) -> None:
    payload: Any = {"posts": posts}
    tmp = posts_path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(posts_path)


def has_post_for_video(posts: list[dict[str, Any]], video_id: str) -> bool:
    for p in posts:
        if (p.get("video_id") or "").strip() == video_id:
            return True
        if video_id and video_id in (p.get("youtube_url") or ""):
            return True
    return False


def fetch_transcript(video_id: str) -> str:
    """
    Fetch transcript via youtube-transcript-api.
    Requires captions to exist (manual or auto). If none, raises.
    """
    # Prefer Supadata (if SUPADATA_KEY set) because it supports many platforms and fallback modes.
    supa_key = (os.environ.get("SUPADATA_KEY") or "").strip()
    if supa_key:
        try:
            from supadata import Supadata  # type: ignore

            client = Supadata(api_key=supa_key)
            # Request plain text transcript when possible
            resp = client.youtube.transcript(video_id=video_id, text=True)
            # Some SDK responses expose .content
            if hasattr(resp, "content"):
                return (resp.content or "").strip()
            # Or a dict-like response
            if isinstance(resp, dict):
                # support either 'content' or 'text' or 'transcript'
                return (resp.get("content") or resp.get("text") or resp.get("transcript") or "").strip()
        except Exception:
            # Fall through to other methods if supadata fails for this video
            pass

    # Fallback: try youtube-transcript-api (local dependency)
    try:
        from youtube_transcript_api import YouTubeTranscriptApi  # type: ignore
    except Exception as e:
        raise RuntimeError("No transcript provider available. Install youtube-transcript-api or set SUPADATA_KEY.") from e

    last_err: Exception | None = None
    for langs in (["en"], ["en-US", "en"], ["en-GB", "en"]):
        try:
            parts = YouTubeTranscriptApi.get_transcript(video_id, languages=langs)
            return " ".join((p.get("text") or "").strip() for p in parts if (p.get("text") or "").strip()).strip()
        except Exception as e:  # noqa: BLE001
            last_err = e
    raise RuntimeError(f"No transcript available for {video_id}.") from last_err


def generate_article_html(title: str, transcript: str, video_url: str, provider: str = "openai") -> dict[str, str]:
    """
    Returns dict with keys: title, description, category, html
    - If OPENAI_API_KEY is set and provider=openai, uses OpenAI API for better writing.
    - Otherwise returns a simple deterministic draft based on transcript.
    """
    provider = (provider or "").strip().lower()
    # Support either OPENAI_API_KEY or OPEN_AI_KEY (user-friendly)
    api_key = (os.environ.get("OPENAI_API_KEY") or os.environ.get("OPEN_AI_KEY") or "").strip()
    # Prefer structured JSON spec from the richer spec endpoint/flow when OpenAI is available.
    if provider == "openai" and api_key:
        try:
            # Ask the LLM to produce a structured JSON spec, then render it to html.
            spec = expand_article_to_json_spec(title=title, transcript=transcript, existing_html="")
            if isinstance(spec, dict):
                rendered = render_article_from_spec(spec)
                return {
                    "title": (spec.get("title") or title).strip(),
                    "description": (spec.get("description") or "").strip(),
                    "category": (spec.get("category") or "CRO").strip(),
                    "html": rendered,
                }
        except Exception:
            # If the structured flow fails, fall back to deterministic draft below.
            pass

    # Deterministic fallback: create a simple structured draft.
    cleaned = re.sub(r"\s+", " ", transcript).strip()
    short = cleaned[:700].strip()
    description = (short[:157] + "...") if len(short) > 160 else short
    html = f"""
<p>{description}</p>
<div class="callout">
  <p class="callout-title">Want help implementing?</p>
  <p class="mb-0">We can audit your funnel and build a prioritized roadmap.</p>
  <div class="mt-6 flex flex-col sm:flex-row gap-3">
    <a class="btn btn-primary" href="/schedule-a-call/">Hire Sparksmetrics</a>
    <button type="button" class="btn btn-primary" data-audit-modal data-title="Get a FREE 24-Hour CRO Audit" data-description="Enter your email and we’ll get in touch to schedule your free audit. Limited to 3 brands per week." data-button-text="Claim my free audit">Claim free CRO audit</button>
    <button type="button" class="btn btn-outline" data-checklist-modal>Download free ebook</button>
  </div>
</div>
<h2>Key points</h2>
<ul>
  <li>Run qualitative research (surveys, recordings, user tests) before you ship ideas.</li>
  <li>Use funnel + segmentation to find where the leak is (device, region, channel).</li>
  <li>Prioritize objectively and keep tests continuously running.</li>
  <li>Write copy that answers objections and differentiates.</li>
  <li>Choose big swings vs small iterations based on site maturity.</li>
</ul>
""".strip()
    return {"title": title.strip(), "description": description, "category": "CRO", "html": html}


def _strip_tags(text: str) -> str:
    return re.sub(r"<[^>]+>", " ", text)


def _build_rich_spec_from_text(title: str, transcript: str, existing_html: str) -> dict:
    """Deterministic rich spec generator when LLM is unavailable."""
    # Remove any embedded JSON-LD fragments from the existing HTML/transcript
    raw = (transcript or existing_html or "") or ""
    raw = re.sub(r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>.*?</script>', "", raw, flags=re.I | re.S)
    raw = re.sub(r'\{\s*"@context"[\s\S]*?\}', "", raw)
    plain = _strip_tags(raw)
    short = (plain.strip() or title).strip()
    description = (short[:157] + "...") if len(short) > 160 else short

    # Simple heuristics to create sections from title keywords
    keywords = [w.capitalize() for w in re.findall(r"[A-Za-z0-9]+", title)][:6]
    intro = f"<p>{description or 'An actionable guide based on the video content.'}</p>"

    sections = []
    # Overview
    sections.append(
        {
            "h2": "Overview",
            "paragraphs": [intro, "<p>This article summarizes the main points and practical steps you can apply today.</p>"],
        }
    )
    # Key lessons
    lessons = []
    lesson_text = "Key lessons and takeaways:"
    for k in keywords[:4]:
        lessons.append(f"Apply the principle of <strong>{k}</strong> where relevant to your funnel.")
    sections.append({"h2": "Key lessons", "paragraphs": [f"<p>{lesson_text}</p>"], "lists": [lessons]})
    # Implementation checklist
    checklist_items = [
        "Run qualitative research: surveys and session recordings",
        "Segment funnels by device and channel",
        "Prioritize tests using ICE or RICE",
        "Optimize copy for clarity and trust",
        "Measure impact and learn iteratively",
    ]
    sections.append({"h2": "Implementation checklist", "paragraphs": ["<p>Use this checklist to get started quickly.</p>"], "lists": [checklist_items]})
    # Examples / Next steps
    sections.append(
        {
            "h2": "Examples & next steps",
            "paragraphs": [
                "<p>Pick one high-impact page and run a quick usability test this week. Use recordings to validate hypotheses before building big changes.</p>"
            ],
        }
    )

    faqs = [
        {"q": "How long will this take?", "a_html": "<p>Small wins in 1-2 weeks; large redesigns require more planning and testing.</p>"},
        {"q": "Do I need developer help?", "a_html": "<p>Often a CRO specialist and minimal dev support suffice for many impactful tests.</p>"},
    ]

    hero = {"kicker": "", "title": title, "lead_html": intro, "cta_text": "Hire Sparksmetrics", "cta_url": "/schedule-a-call/"}

    return {
        "title": title,
        "description": description,
        "hero": hero,
        "stats": [],
        "sections": sections,
        "checklist": checklist_items,
        "faqs": faqs,
        "closing_html": '<p><a class="btn btn-primary" href="/schedule-a-call/">Schedule a call</a></p>',
    }


def _word_count_html(html: str) -> int:
    text = _strip_tags(html)
    return len(re.findall(r"\w+", text))


def _call_openai_responses(prompt: str, model: str, api_key: str, timeout: int = 120) -> dict:
    base = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    # First: try the Responses API (preferred)
    try:
        url = f"{base}/responses"
        payload = {
            "model": model,
            "input": [
                {"role": "system", "content": "You are a helpful SEO writing assistant."},
                {"role": "user", "content": prompt},
            ],
            "text": {"format": {"type": "json_object"}},
            # Request a larger response budget when available
            "max_output_tokens": 8000,
            "temperature": 0.0,
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}, method="POST")
        ctx = ssl.create_default_context()
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            return json.load(resp)
    except Exception:
        # Fallback: try Chat Completions (more widely supported)
        try:
            try:
                import requests as _requests  # type: ignore
            except Exception:
                _requests = None
            if _requests is None:
                raise
            url = f"{base}/chat/completions"
            payload = {
                "model": model,
                "messages": [
                    {"role": "system", "content": "You are a helpful SEO writing assistant."},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.0,
                "max_tokens": 8000,
            }
            headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
            r = _requests.post(url, json=payload, headers=headers, timeout=timeout)
            r.raise_for_status()
            data = r.json()
            # Normalize to a shape _parse_responses_output expects
            msg = ""
            choices = data.get("choices") or []
            if isinstance(choices, list) and choices:
                first = choices[0]
                if isinstance(first, dict):
                    # Chat-style
                    msg = (first.get("message") or {}).get("content") or first.get("text") or ""
            return {"output_text": msg, "output": [{"content": msg}]}
        except Exception:
            # Re-raise original failure to surface to caller
            raise


def _parse_responses_output(resp: dict) -> dict | None:
    if not isinstance(resp, dict):
        return None
    out_text = resp.get("output_text") or ""
    if out_text:
        try:
            return json.loads(out_text)
        except Exception:
            # Attempt to extract a JSON object from the text (first "{" .. last "}")
            try:
                first = out_text.find("{")
                last = out_text.rfind("}")
                if first != -1 and last != -1 and last > first:
                    candidate = out_text[first : last + 1]
                    return json.loads(candidate)
            except Exception:
                pass
            return {"html": out_text}
    # fallback: try reading output array
    out = resp.get("output") or resp.get("choices") or []
    texts = []
    if isinstance(out, list):
        for item in out:
            if isinstance(item, dict):
                txt = item.get("content") or item.get("text") or item.get("message") or ""
                if isinstance(txt, str):
                    texts.append(txt)
    joined = "\n".join(texts).strip()
    if not joined:
        return None
    try:
        return json.loads(joined)
    except Exception:
        # Try to extract JSON substring if the model wrapped it in text
        try:
            first = joined.find("{")
            last = joined.rfind("}")
            if first != -1 and last != -1 and last > first:
                candidate = joined[first : last + 1]
                return json.loads(candidate)
        except Exception:
            pass
        return {"html": joined}


def expand_article_with_openai(title: str, transcript: str, existing_html: str, model: str = "gpt-4.1-mini") -> dict:
    api_key = (os.environ.get("OPENAI_API_KEY") or os.environ.get("OPEN_AI_KEY") or "").strip()
    if not api_key:
        raise RuntimeError("OpenAI key not set")
    prompt = f"""
You are an expert SEO writer for an agency. Expand and rewrite the following article (HTML fragment) into a detailed, practical, original article of at least 1000 words, suitable for publishing on Sparksmetrics. Keep formatting as HTML fragment (use <h2>, <h3>, <p>, <ul>, <ol>, <blockquote>, <pre> where helpful). Include practical examples, step-by-step checks, and an implementation checklist. Include at least one internal CTA to /schedule-a-call/ and one CTA to download the ebook (use the existing data-checklist-modal/button patterns). Do not include <article> wrapper. Return a JSON object with keys: title, description (<=160 chars), html.

Transcript (for reference):
{transcript[:12000]}

Existing article HTML (for reference):
{existing_html[:4000]}
"""
    resp = _call_openai_responses(prompt, model, api_key)
    parsed = _parse_responses_output(resp)
    if not parsed:
        raise RuntimeError("OpenAI did not return usable output")
    return parsed


def expand_article_to_json_spec(title: str, transcript: str, existing_html: str, model: str = OPENAI_MODEL_DEFAULT) -> dict:
    """Ask the LLM to return a structured JSON spec for the article (hero, sections, tips, stats, checklist, faqs)."""
    api_key = (os.environ.get("OPENAI_API_KEY") or os.environ.get("OPEN_AI_KEY") or "").strip()
    if not api_key:
        raise RuntimeError("OpenAI key not set")
    max_chunk = 12000
    chunks = [transcript[i:i+max_chunk] for i in range(0, len(transcript), max_chunk)] if transcript else []
    transcript_parts = ""
    for idx, c in enumerate(chunks, 1):
        transcript_parts += f"\n\n--- TRANSCRIPT PART {idx}/{len(chunks)} ---\n{c}\n"
    # Build prompt template and substitute transcript/existing_html/title to avoid f-string brace interpolation issues.
    spec_template = """
You are an expert SEO content strategist and conversion copywriter. Produce a structured JSON specification for a long-form, publication-ready article based on the video transcript and existing draft.

Return a single JSON object (strict JSON, no extra text) with these keys:
- title: string (human-friendly headline)
- description: string (<=160 chars)
- hero: { kicker, title, lead_html, cta_text, cta_url }
- stats: [ { value, label } ... ] (0-3 items)
- sections: [ { h2, h3s:[...], paragraphs:[...], tips:[...], lists:[...] } ... ]  (4-6 substantive sections)
- checklist: [string,...]
- faqs: [ { q, a_html } ]
- closing_html: string (final CTA + summary)

Hard requirements (MUST follow exactly):
- The final rendered article (when your html fragments are concatenated) MUST be at least 1000 words. If your first output is shorter, expand sections and paragraphs until the word count is satisfied.
- Title: must be a readable headline (do NOT return the raw video id). If you cannot create a better headline, use the provided title exactly.
- Hero: include a hero.title and lead_html containing 2 short paragraphs (about 40–70 words each) that hook the reader and promise a clear benefit.
- Sections: provide 4–6 substantive sections. Each section must include:
  - h2: a descriptive heading
  - paragraphs: an array of 3–6 paragraphs per section (each ~40–80 words) with concrete examples, steps, and micro-checks
  - optionally h3s, tips (short 1–2 sentence actionable callouts), and lists (explicit step lists)
- Checklist: include 5–10 concrete checklist items with optional time estimates (e.g. "5–10 min", "1 day").
- FAQs: include 2–4 common questions with concise helpful answers.
- Closing_html: include a short final CTA using site classes (btn, btn-primary, btn-outline).
- Tone: direct, practical, punchy. Use short paragraphs and specific, measurable advice. Do NOT include AI meta-commentary (e.g., "as an AI").
- Output: produce STRICTLY valid JSON only.

Provide one short example of the expected JSON structure (for format only — follow it exactly, but replace the example content with content derived from the transcript):
{
  "title": "Example headline",
  "description": "Short summary...",
  "hero": { "kicker": "KICK", "title": "Example headline", "lead_html": "<p>Lead paragraph 1</p><p>Lead paragraph 2</p>", "cta_text": "Hire", "cta_url": "/schedule-a-call/" },
  "sections": [
    { "h2": "Section heading", "paragraphs": ["<p>Paragraph 1</p>", "<p>Paragraph 2</p>", "<p>Paragraph 3</p>"], "tips": ["One short tip"], "lists": [["step 1","step 2"]] }
  ],
  "checklist": ["Do X (5–10 min)","Do Y (1 day)"],
  "faqs": [{"q":"Q?","a_html":"<p>A.</p>"}],
  "closing_html": "<p><a class=\"btn btn-primary\" href=\"/schedule-a-call/\">Schedule a call</a></p>"
}

Provide transcript for reference:
TRANSCRIPT_PARTS_PLACEHOLDER

Existing draft (for reference):
EXISTING_HTML_PLACEHOLDER

Also: the article should use this TITLE as the canonical title if you generate one: "TITLE_PLACEHOLDER".
If you cannot produce a better human-friendly title, set the top-level "title" field to the provided TITLE.
Return strictly valid JSON. Use only the site's CSS classes for HTML fragments.
"""
    spec_prompt = spec_template.replace("TRANSCRIPT_PARTS_PLACEHOLDER", transcript_parts).replace(
        "EXISTING_HTML_PLACEHOLDER", existing_html[:4000]
    ).replace("TITLE_PLACEHOLDER", title)
    resp = _call_openai_responses(spec_prompt, model, api_key)
    parsed = _parse_responses_output(resp)
    if not parsed:
        # Use deterministic rich spec generator for reliable, styled content
        return _build_rich_spec_from_text(title=title, transcript=transcript, existing_html=existing_html)

    # Ensure minimal required fields exist and fall back to provided title/description when missing
    if isinstance(parsed, dict):
        if not parsed.get("title"):
            parsed["title"] = title
        if not parsed.get("description"):
            # Derive short description from transcript or title
            plain = re.sub(r"<[^>]+>", " ", (transcript or existing_html or title))
            snippet = (plain.strip() or title)[:157]
            parsed["description"] = (snippet + "...") if len(snippet) >= 160 else snippet
        # Ensure sections list exists
        if not isinstance(parsed.get("sections"), list):
            parsed["sections"] = []
    # If the returned spec is too short, attempt one automatic rewrite request to reach >=1000 words.
    try:
        if isinstance(parsed, dict):
            rendered = render_article_from_spec(parsed)
            wc = _word_count_html(rendered)
            if wc < 1000:
                # Ask the LLM to expand the JSON spec to reach >=1000 words, returning valid JSON.
                repair_prompt = (
    'Please produce an improved structured JSON specification for the article that is at least 1000 words when rendered.\n'
    'Use the same keys as before (title, description, hero, stats, sections, checklist, faqs, closing_html).\n'
    'Here is the previous JSON spec (improve it, keep structure):\n' + json.dumps(parsed, ensure_ascii=False) + '\n\n'
    'Transcript for reference:\n' + transcript_parts + '\n\n'
    'Rules:\n- Return strictly valid JSON only.\n- Make sections substantially longer: each section should contain 3-6 paragraphs of ~40-80 words each, including examples and actionable steps.\n'
)

                resp2 = _call_openai_responses(repair_prompt, model, api_key)
                parsed2 = _parse_responses_output(resp2)
                if isinstance(parsed2, dict):
                    parsed = parsed2
    except Exception:
        # Best-effort: ignore repair failures and return original parsed
        pass
    # Final sanity fixes (ensure required fields exist)
    if isinstance(parsed, dict):
        if not parsed.get("title"):
            parsed["title"] = title
        if not parsed.get("description"):
            plain = re.sub(r"<[^>]+>", " ", (transcript or existing_html or title))
            snippet = (plain.strip() or title)[:157]
            parsed["description"] = (snippet + "...") if len(snippet) >= 160 else snippet
        if not isinstance(parsed.get("sections"), list):
            parsed["sections"] = []
    return parsed

def render_article_from_spec(spec: dict) -> str:
    """Render the JSON spec to an HTML fragment using site classes."""
    parts = []
    # JSON-LD
    meta = {
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": spec.get("title"),
        "description": spec.get("description"),
    }
    parts.append(f'<script type="application/ld+json">{json.dumps(meta)}</script>')

    # Hero
    hero = spec.get("hero") or {}
    if hero:
        kicker = hero.get("kicker") or ""
        htitle = hero.get("title") or spec.get("title") or ""
        lead = hero.get("lead_html") or ""
        cta_text = hero.get("cta_text") or "Hire Sparksmetrics"
        cta_url = hero.get("cta_url") or "/schedule-a-call/"
        parts.append(f'<div class="article-hero"><div class="kicker">{kicker}</div><h2>{htitle}</h2><p class="lead">{lead}</p><a class="btn btn-primary" href="{cta_url}">{cta_text}</a></div>')

    # Stats
    stats = spec.get("stats") or []
    if stats:
        parts.append('<div class="stat-grid">')
        for s in stats[:3]:
            parts.append(f'<div class="stat-card"><div class="text-3xl font-black">{s.get("value")}</div><div class="text-sm text-gray-600">{s.get("label")}</div></div>')
        parts.append('</div>')

    # Sections
    for i, sec in enumerate(spec.get("sections") or [], 1):
        h2 = sec.get("h2") or f"Section {i}"
        parts.append(f'<h2>{h2}<span id="toc-{i}"></span></h2>')
        for p in sec.get("paragraphs") or []:
            parts.append(f'<p>{p}</p>')
        for tip in sec.get("tips") or []:
            parts.append(f'<div class="tip-banner"><strong>Tip:</strong> {tip}</div>')
        for lst in sec.get("lists") or []:
            parts.append("<ul>")
            for li in lst:
                parts.append(f"<li>{li}</li>")
            parts.append("</ul>")
        for h3 in sec.get("h3s") or []:
            parts.append(f'<h3>{h3}</h3>')

    # Checklist
    checklist = spec.get("checklist") or []
    if checklist:
        parts.append('<section class="mt-10 p-6 bg-light-base border border-gray-200 rounded-2xl"><h3>Implementation checklist</h3><ul>')
        for item in checklist:
            parts.append(f"<li>{item}</li>")
        parts.append("</ul></section>")

    # FAQs
    faqs = spec.get("faqs") or []
    if faqs:
        parts.append("<section class='mt-8'><h3>FAQs</h3>")
        for f in faqs:
            parts.append(f"<h4>{f.get('q')}</h4><p>{f.get('a_html')}</p>")
        parts.append("</section>")

    # Closing
    closing = spec.get("closing_html") or ""
    if closing:
        parts.append(closing)

    # Ensure final CTA presence
    if "/schedule-a-call/" not in "".join(parts):
        parts.append('<div class="callout"><p class="callout-title">Ready to act?</p><a class="btn btn-primary" href="/schedule-a-call/">Book your free CRO audit</a></div>')

    return "\n".join(parts)


def _html_text_snippets(html: str, n_chars: int = 1000) -> str:
    """Roughly strip tags to get first text snippet (naive)."""
    # Remove tags
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:n_chars]


def score_article(html: str, title: str, description: str, threshold_keyword: str | None = None) -> tuple[int, dict]:
    """
    Return (score, breakdown). Score out of 100.
    Simple checks mapped to weights.
    """
    breakdown: dict[str, int] = {}
    total = 0

    # Word count -> up to 15 points (700+ words full points)
    words = len(re.findall(r"\w+", re.sub(r"<[^>]+>", " ", html)))
    wc_pts = min(15, int(15 * min(1.0, words / 700)))
    breakdown["word_count"] = wc_pts
    total += wc_pts

    # Title length -> 10 points if between 40 and 70 chars
    tlen = len(title or "")
    title_pts = 10 if 40 <= tlen <= 70 else (5 if 30 <= tlen < 40 or 70 < tlen <= 80 else 0)
    breakdown["title_length"] = title_pts
    total += title_pts

    # Meta description length -> 10 points if 120-160 chars
    dlen = len(description or "")
    meta_pts = 10 if 120 <= dlen <= 160 else (5 if 100 <= dlen < 120 or 160 < dlen <= 180 else 0)
    breakdown["meta_description"] = meta_pts
    total += meta_pts

    # H2 count -> 10 points if >=3
    h2_count = len(re.findall(r"<h2\b", html, flags=re.I))
    h2_pts = 10 if h2_count >= 3 else (5 if h2_count == 2 else 0)
    breakdown["h2_count"] = h2_pts
    total += h2_pts

    # Keyword presence in title + first paragraph -> 10 points
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
        # No explicit keyword: small partial credit if title present
        kw_pts = 5 if title else 0
    breakdown["keyword_presence"] = kw_pts
    total += kw_pts

    # Internal links (to / pages) -> 10 points if >=1
    internal_links = re.findall(r'href=["\'](/[^"\']+)["\']', html)
    int_pts = 10 if len(internal_links) >= 1 else 0
    breakdown["internal_links"] = int_pts
    total += int_pts

    # External authoritative links -> 5 points if >=1
    external_links = re.findall(r'href=["\']https?://([^"\']+)["\']', html)
    # exclude links to own domain (heuristic)
    external_filtered = [u for u in external_links if "sparksmetrics" not in u.lower()]
    ext_pts = 5 if len(external_filtered) >= 1 else 0
    breakdown["external_links"] = ext_pts
    total += ext_pts

    # Images with alt -> 5 points if all images have alt and at least 1 image
    img_tags = re.findall(r"<img\b[^>]*>", html, flags=re.I)
    img_with_alt = [t for t in img_tags if re.search(r'\balt=["\'].*?["\']', t, flags=re.I)]
    img_pts = 0
    if img_tags:
        img_pts = 5 if len(img_with_alt) == len(img_tags) else 2
    breakdown["images_alt"] = img_pts
    total += img_pts

    # Table of contents presence (simple check for <nav id="toc" or "Table of contents")
    toc = 5 if re.search(r"(Table of contents|<nav[^>]+toc|id=[\"']toc[\"'])", html, flags=re.I) else 0
    breakdown["toc"] = toc
    total += toc

    # Avoid generic AI phrases (naive): penalize if found
    ai_phrases = ["as an ai", "as an ai language model", "in this article we will", "in this post i"]
    ai_found = any(p in html.lower() for p in ai_phrases)
    ai_pts = 0 if ai_found else 5
    breakdown["ai_phrases"] = ai_pts
    total += ai_pts

    # Schema presence (article JSON-LD) -> 5 points
    schema_pts = 5 if re.search(r"application/ld\+json", html, flags=re.I) else 0
    breakdown["schema"] = schema_pts
    total += schema_pts

    # Mobile/responsive assumed by template -> 5 points
    breakdown["mobile"] = 5
    total += 5

    # Engagement/trust signals (author, references) -> 10 points if author or references found
    author_found = bool(re.search(r'author|byline|class=["\']author', html, flags=re.I))
    references_found = bool(re.search(r"references|sources|cite", html, flags=re.I))
    trust_pts = 10 if author_found and references_found else (5 if author_found or references_found else 0)
    breakdown["trust_signals"] = trust_pts
    total += trust_pts

    # Cap at 100
    score = min(100, int(total))
    return score, breakdown


def build_post_template(video_id: str, post: dict[str, Any], article_html: str) -> str:
    """Return full Jinja template for a video-based post."""
    # Use post dict fields for head tags. Video embed uses post.video_id to keep template reusable.
    return f"""{{% extends "base.html" %}}
{{% block title %}}{{{{ post.title }}}} | Sparksmetrics{{% endblock %}}
{{% block meta_description %}}{{{{ post.description }}}}{{% endblock %}}
{{% block og_title %}}{{{{ post.title }}}}{{% endblock %}}
{{% block twitter_title %}}{{{{ post.title }}}}{{% endblock %}}
{{% block og_description %}}{{{{ post.description }}}}{{% endblock %}}
{{% block twitter_description %}}{{{{ post.description }}}}{{% endblock %}}

{{% block content %}}
<section class="bg-light-base py-10 md:py-14 border-b border-gray-100">
  <div class="content-narrow px-6">
    <a href="{{{{ url_for('main.blog_index') }}}}" class="inline-flex items-center gap-2 text-[10px] font-black uppercase tracking-widest text-gray-500 hover:text-primary transition-colors min-h-[44px]">
      <span class="material-symbols-outlined text-base" aria-hidden="true">arrow_back</span>
      Back to blog
    </a>

    <header class="mt-6">
      <p class="text-primary font-bold text-sm uppercase tracking-[0.4em] mb-4">{{{{ post.category }}}}</p>
      <h1 class="normal-case text-3xl md:text-5xl font-display font-black tracking-tight text-deep-charcoal mb-4">{{{{ post.title }}}}</h1>
      <p class="text-gray-600 text-base md:text-lg mb-0">{{{{ post.description }}}}</p>
      <div class="mt-6 flex flex-wrap gap-2">
        <span class="inline-flex items-center px-3 py-2 rounded-lg bg-white border border-gray-200 text-gray-500 text-[10px] font-bold uppercase tracking-widest">Published {{{{ post.published_date }}}}</span>
        <span class="inline-flex items-center px-3 py-2 rounded-lg bg-white border border-gray-200 text-gray-500 text-[10px] font-bold uppercase tracking-widest">{{{{ post.reading_time }}}}</span>
      </div>
    </header>
  </div>
</section>

<section class="bg-light-base py-12 md:py-16">
  <div class="content-narrow px-6">
    <div class="aspect-video w-full rounded-2xl overflow-hidden bg-black border border-black/10">
      <iframe
        class="w-full h-full"
        src="https://www.youtube.com/embed/{{{{ post.video_id or '{video_id}' }}}}"
        title="YouTube video player"
        frameborder="0"
        loading="lazy"
        referrerpolicy="strict-origin-when-cross-origin"
        allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"
        allowfullscreen
      ></iframe>
    </div>

    <article class="blog-prose mt-10">
{article_html}
    </article>
  </div>
</section>
{{% endblock %}}
"""


def slack_notify(webhook_url: str, text: str) -> None:
    webhook_url = (webhook_url or "").strip()
    if not webhook_url:
        return
    try:
        import requests  # type: ignore
    except Exception:
        return
    try:
        requests.post(webhook_url, json={"text": text}, timeout=10).raise_for_status()
    except Exception:
        return


def main() -> int:
    parser = argparse.ArgumentParser(description="Auto-generate blog posts from new YouTube videos.")
    parser.add_argument("--channel", default="", help="YouTube channel ID (starts with UC...)")
    parser.add_argument("--video", default="", help="YouTube video ID or URL to process a single video")
    parser.add_argument("--max-results", type=int, default=5, help="How many latest videos to check")
    parser.add_argument("--dry-run", action="store_true", help="Do not write files; just print what would happen")
    parser.add_argument("--force", action="store_true", help="Force publish even if SEO score is below threshold")
    parser.add_argument("--provider", default=os.environ.get("BLOG_WRITER_PROVIDER", "openai"), help="Writer provider: openai|none")
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parents[1]
    _load_env(project_root)

    channel_id = (args.channel or os.environ.get("YOUTUBE_CHANNEL_ID") or "").strip()
    video_arg = (args.video or "").strip()

    posts_path = project_root / "app" / "blog_posts.json"
    templates_dir = project_root / "app" / "templates"

    posts = load_blog_posts(posts_path)

    videos: list[YouTubeVideo] = []
    if video_arg:
        # Extract video id if a full URL was provided
        m = re.search(r"(?:v=|youtu\\.be/|/embed/)([A-Za-z0-9_-]{11})", video_arg)
        vid = m.group(1) if m else (video_arg if re.fullmatch(r"[A-Za-z0-9_-]{11}", video_arg) else "")
        if not vid:
            raise SystemExit("Invalid video id or URL passed to --video")
        # Try to fetch metadata via Supadata if available, else fall back
        title = vid
        published = datetime.now(timezone.utc).strftime("%d %b %Y").lstrip("0")
        supa_key = (os.environ.get("SUPADATA_KEY") or "").strip()
        if supa_key:
            try:
                from supadata import Supadata  # type: ignore

                client = Supadata(api_key=supa_key)
                info = client.youtube.video(id=vid)
                # Try common attributes
                title = getattr(info, "title", None) or info.get("title") if isinstance(info, dict) else title
                published_raw = getattr(info, "published_at", None) or (info.get("published_at") if isinstance(info, dict) else None)
                if published_raw:
                    try:
                        dt = datetime.fromisoformat(published_raw.replace("Z", "+00:00"))
                        published = dt.strftime("%d %b %Y").lstrip("0")
                    except Exception:
                        published = published
            except Exception:
                # ignore failures; we'll continue with best-effort metadata
                pass
        videos = [YouTubeVideo(video_id=vid, title=str(title), url=f"https://youtu.be/{vid}", published=published)]
    else:
        if not channel_id:
            raise SystemExit("Missing channel id. Pass --channel UC... or set YOUTUBE_CHANNEL_ID in .env")
        videos = fetch_latest_videos(channel_id, max_results=max(1, args.max_results))
    if not videos:
        print("No videos found (RSS fetch failed).")
        return 0

    created: list[dict[str, Any]] = []
    for v in videos:
        if has_post_for_video(posts, v.video_id):
            continue

        try:
            transcript = fetch_transcript(v.video_id)
        except Exception as e:
            # If transcript isn't available, proceed with an empty transcript
            # so deterministic fallback drafts can still be created.
            msg = f"Transcript unavailable for {v.video_id}; continuing with empty transcript. ({type(e).__name__}: {e})"
            if args.dry_run:
                print(f"[dry-run] {msg}")
            else:
                print(msg)
            transcript = ""
        # Generate initial draft (prefer provider from args)
        gen = generate_article_html(title=v.title, transcript=transcript, video_url=v.url, provider=args.provider)

        # If draft is thin, expand using OpenAI to >= BLOG_MIN_WORDS when possible
        article_html_candidate = gen.get("html") or ""
        wc = _word_count_html(article_html_candidate)
        min_words = int(os.environ.get("BLOG_MIN_WORDS", str(BLOG_MIN_WORDS_DEFAULT)))
        if wc < min_words:
            api_key = (os.environ.get("OPENAI_API_KEY") or os.environ.get("OPEN_AI_KEY") or "").strip()
            if api_key:
                try:
                    if args.dry_run:
                        print(f"[dry-run] Draft {wc} words < {min_words}, requesting OpenAI expansion")
                    expanded = expand_article_with_openai(title=v.title, transcript=transcript, existing_html=article_html_candidate, model=(os.environ.get("OPENAI_MODEL") or "gpt-4.1-mini"))
                    # merge expanded output
                    if isinstance(expanded, dict) and expanded.get("html"):
                        gen["html"] = expanded.get("html")
                        gen["title"] = expanded.get("title") or gen.get("title")
                        gen["description"] = expanded.get("description") or gen.get("description")
                        article_html_candidate = gen.get("html")
                        wc = _word_count_html(article_html_candidate)
                        if args.dry_run:
                            print(f"[dry-run] Expanded draft now {wc} words")
                except Exception as e:
                    if args.dry_run:
                        print(f"[dry-run] OpenAI expansion failed: {e}")
                    else:
                        slack_notify((os.environ.get("SLACK_WEBHOOK_URL") or "").strip(), f"Auto-blog expansion failed for {v.video_id}: {e}")
            else:
                # No OpenAI key: fall back to deterministic enrichment or flag for review
                if args.dry_run:
                    print(f"[dry-run] Draft {wc} words < {min_words} and no OpenAI key — will flag for review")
                else:
                    slack_notify((os.environ.get("SLACK_WEBHOOK_URL") or "").strip(), f"Auto-blog draft for {v.video_id} is {wc} words (<{min_words}) and needs human expansion.")

        # SEO scoring and optional rewrites (existing behavior)
        publish_threshold = int(os.environ.get("BLOG_PUBLISH_THRESHOLD", str(BLOG_PUBLISH_THRESHOLD_DEFAULT)))
        force_publish = bool(args.force)
        # Derive primary keyword from title (naive: remove stopwords later if needed)
        primary_kw = re.sub(r"[^a-z0-9\s]", "", v.title.lower()).split()
        keyword = primary_kw[0] if primary_kw else ""
        article_html_candidate = gen.get("html") or ""
        score, breakdown = score_article(article_html_candidate, gen.get("title") or v.title, gen.get("description") or "", threshold_keyword=keyword)
        attempts = 0
        used_provider = args.provider
        # If score below threshold and we have OpenAI available, try one rewrite with OpenAI
        while score < publish_threshold and attempts < 2 and (os.environ.get("OPENAI_API_KEY") or os.environ.get("OPEN_AI_KEY")):
            attempts += 1
            if args.dry_run:
                print(f"[dry-run] SEO score {score} below threshold {publish_threshold}; attempting rewrite with OpenAI (attempt {attempts})")
            gen = generate_article_html(title=v.title, transcript=transcript, video_url=v.url, provider="openai")
            article_html_candidate = gen.get("html") or ""
            score, breakdown = score_article(article_html_candidate, gen.get("title") or v.title, gen.get("description") or "", threshold_keyword=keyword)
            used_provider = "openai"

        if not force_publish and score < publish_threshold:
            # Do not publish; notify Slack with report
            msg_lines = [
                f"Auto-blog DID NOT publish: {v.title} ({v.video_id})",
                f"Score: {score}/{publish_threshold}",
                "Breakdown:",
            ]
            for k, vpts in breakdown.items():
                msg_lines.append(f"- {k}: {vpts}")
            msg = "\n".join(msg_lines)
            if args.dry_run:
                print("[dry-run] " + msg)
            else:
                slack_notify((os.environ.get("SLACK_WEBHOOK_URL") or "").strip(), msg)
            # Skip publishing this video
            continue

        slug = slugify(gen["title"])
        template_name = f"blog_{slug}.html"
        template_path = templates_dir / template_name

        description = (gen.get("description") or "").strip()[:160]
        reading_time = estimate_reading_time(transcript)
        category = (gen.get("category") or "CRO").strip() or "CRO"

        post = {
            "slug": slug,
            "title": gen["title"].strip() or v.title,
            "description": description or f"Insights from: {v.title}",
            "published_date": v.published,
            "updated_date": v.published,
            "reading_time": reading_time,
            "category": category,
            "template": template_name,
            "video_id": v.video_id,
            "youtube_url": v.url,
            "source": "youtube",
        }

        article_html = gen.get("html") or ""
        # Indent nicely inside <article>
        article_html = "\n".join("      " + line if line.strip() else "" for line in article_html.splitlines()).rstrip() + "\n"
        template = build_post_template(video_id=v.video_id, post=post, article_html=article_html)

        if args.dry_run:
            print(f"[dry-run] Would create {template_path} and append to {posts_path}: {slug}")
        else:
            template_path.write_text(template, encoding="utf-8")
            posts.insert(0, post)  # newest first
            save_blog_posts(posts_path, posts)

        created.append(post)

        # One post per run by default (avoid mass generation on first install)
        break

    if created:
        site_base = (os.environ.get("SITE_BASE_URL") or "https://sparksmetrics.com").rstrip("/")
        webhook = (os.environ.get("SLACK_WEBHOOK_URL") or "").strip()
        for post in created:
            url = f"{site_base}/blog/{post['slug']}"
            text = f"New blog post created from YouTube upload: *{post['title']}*\\n{url}\\nVideo: {post.get('youtube_url')}"
            if args.dry_run:
                print(f"[dry-run] Slack message: {text}")
            else:
                slack_notify(webhook, text)
        return 0

    print("No new videos to post.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

