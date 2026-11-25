"""Video autopilot: every new long YouTube video becomes a page at /videos/<slug>.

Run daily (systemd timer on the droplet, see deploy/sparksmetrics-video-autopilot.*):

    ./venv/bin/python tasks/video_autopilot.py

For every long video in the channel RSS feed published on/after VIDEO_AUTOPILOT_SINCE that
has no page yet, it fetches the captions (TranscriptAPI), asks Claude for the page content
(summary, takeaways, chapters, article, FAQ, cleaned transcript), validates it and writes
<slug>.json into the autopilot folder (instance/video_pages/, not in git). The site picks the
file up on the next request; /videos, the sitemap and llms.txt list it automatically.

Options:
    --video ID      build (or rebuild with --force) one video, ignoring the date filter
    --out DIR       write here instead of instance/video_pages (used to seed app/video_pages)
    --dry-run       list what would be built, call nothing paid
    --limit N       at most N pages per run (default 3)

Env: TRANSCRIPT_API_KEY, ANTHROPIC_API_KEY, optional SLACK_WEBHOOK_URL, SITE_BASE_URL,
YOUTUBE_CHANNEL_ID, VIDEO_AUTOPILOT_SINCE (YYYY-MM-DD), VIDEO_AUTOPILOT_MODEL.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except ImportError:
    pass

from app.video_pages import AUTO_DIR, SEED_DIR, load_video_pages, slugify  # noqa: E402

log = logging.getLogger("video_autopilot")

CHANNEL_ID = os.environ.get("YOUTUBE_CHANNEL_ID") or "UCkwylcLXJiV-kQxCZMRR-tw"
TRANSCRIPT_URL = "https://transcriptapi.com/api/v2/youtube/transcript"
USER_AGENT = "sparksmetrics-video-autopilot/1.0"
MIN_LONG_SECONDS = 180
STATE_FILE = ROOT / "instance" / "video_autopilot_state.json"
MAX_ATTEMPTS = 3


class AutopilotError(Exception):
    pass


class TranscriptNotReady(AutopilotError):
    pass


# --------------------------------------------------------------------------- schema

def _s():
    return {"type": "string"}


def _obj(props: dict) -> dict:
    return {"type": "object", "properties": props, "required": list(props), "additionalProperties": False}


def _arr(items: dict) -> dict:
    return {"type": "array", "items": items}


OUTPUT_SCHEMA = _obj(
    {
        "title": _s(),
        "meta_title": _s(),
        "meta_description": _s(),
        "teaser": _s(),
        "summary": _s(),
        "key_takeaways": _arr(_s()),
        "stats": _arr(_obj({"value": _s(), "label": _s()})),
        "chapters": _arr(_obj({"t": {"type": "integer"}, "title": _s()})),
        "sections": _arr(
            _obj(
                {
                    "heading": _s(),
                    "t": {"type": "integer"},
                    "blocks": _arr(
                        _obj(
                            {
                                "type": {"type": "string", "enum": ["p", "ul", "ol", "quote"]},
                                "text": _s(),
                                "items": _arr(_s()),
                            }
                        )
                    ),
                }
            )
        ),
        "faq": _arr(_obj({"q": _s(), "a": _s()})),
        "tags": _arr(_s()),
        "transcript": _arr(_obj({"t": {"type": "integer"}, "text": _s()})),
    }
)

SYSTEM_PROMPT = """You write the companion web page for each new long-form YouTube video by Stijn Wollerich, founder of Sparksmetrics, a CRO and analytics agency for D2C Shopify brands (worked on 200+ brands, runs A/B tests end to end: research, design, development, analysis). The page lives at sparksmetrics.com/videos/<slug>. It has two jobs: rank in Google for what the video is about, and be the source AI assistants (ChatGPT, Perplexity, Google AI Overviews) quote when someone asks that question. A reader who never presses play must get the full value of the video.

Write in Stijn's voice: first person, direct, practical, a practitioner talking to a Shopify brand owner or ecommerce manager. Plain words. Short paragraphs (2-4 sentences). Concrete numbers and examples from the video. No hype.

Hard rules:
- Everything comes from the video. Never invent numbers, client names, results, tools or claims Stijn did not make. If he gives a number, use it exactly.
- Never use the em dash character. Use commas, colons, full stops or parentheses.
- No AI filler: no "In today's fast-paced world", "let's dive in", "game-changer", "unlock", "elevate", "in conclusion", "it's not X, it's Y" constructions, rhetorical one-line closers, or stacked triads.
- Do not mention "this article", "this page" or "the transcript". You may refer to "the video".
- Keep client names only if Stijn says them on camera.

Return:
- title: the H1. Search-friendly and specific, close to the YouTube title but readable as an article title (max ~70 chars).
- meta_title: max 60 chars, main keyword first.
- meta_description: 140-155 chars, says what the reader learns.
- teaser: one sentence (max ~130 chars) for the video card on /videos.
- summary: the direct answer, 2-3 sentences, written so an AI assistant could quote it on its own. Lead with the core claim.
- key_takeaways: 4-7 bullets, each one concrete and self-contained (a reader should be able to act on it).
- stats: 0-4 striking numbers Stijn states in the video, value short ("76%", "$58k", "90 days"), label one short line. Empty list if there are no real numbers.
- chapters: 5-10 chapters covering the whole video. t = start second (integer, from the caption timestamps), title = short chapter name.
- sections: the article body, 4-8 sections in video order. heading = an H2 phrased the way people search or ask (questions are good). t = the second in the video where that part starts. blocks: paragraphs ("p", text, items = []), bullet lists ("ul"), numbered steps ("ol") with items and text = "" , or a short verbatim quote from Stijn ("quote", text = the quote, items = []). Use **double asterisks** around a few key phrases for bold. Explain the reasoning and the how-to in more depth than a summary: this is the part that ranks. Around 900-1600 words in total across sections.
- faq: 4-6 questions people actually type into Google or ask ChatGPT about this topic, each answered in 2-4 sentences from the video's content.
- tags: 2-5 short topic tags from this set where they fit, others only if needed: "Shopify CRO", "A/B testing", "Product pages", "Checkout", "Analytics", "Paid ads", "AI", "Agency", "Case study", "Ecommerce strategy".
- transcript: the full transcript in blocks of roughly 45-75 seconds. t = start second of the block (integer, from the caption timestamps). Fix only punctuation, capitalisation, paragraphing and obvious speech-recognition errors (brand names like Shopify, Klaviyo, Microsoft Clarity, GA4, Sparksmetrics). Do not summarise, skip or reword what Stijn says. Use commas instead of em dashes here too.
"""


# --------------------------------------------------------------------------- state

def _load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            log.warning("Unreadable state file, starting fresh")
    return {}


def _save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")


# --------------------------------------------------------------------------- inputs

def fetch_feed() -> list[dict]:
    """Latest uploads from the channel RSS feed (no API key). Shorts are marked by their /shorts/ link."""
    url = f"https://www.youtube.com/feeds/videos.xml?channel_id={CHANNEL_ID}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=20) as resp:
        root = ET.fromstring(resp.read())
    ns = {
        "a": "http://www.w3.org/2005/Atom",
        "yt": "http://www.youtube.com/xml/schemas/2015",
        "m": "http://search.yahoo.com/mrss/",
    }
    videos = []
    for entry in root.findall("a:entry", ns):
        vid = entry.findtext("yt:videoId", default="", namespaces=ns).strip()
        link = (entry.find("a:link", ns).get("href") if entry.find("a:link", ns) is not None else "") or ""
        desc = entry.find("m:group/m:description", ns)
        videos.append(
            {
                "youtube_id": vid,
                "title": entry.findtext("a:title", default="", namespaces=ns).strip(),
                "published": entry.findtext("a:published", default="", namespaces=ns).strip(),
                "description": (desc.text or "").strip() if desc is not None else "",
                "is_short": "/shorts/" in link,
            }
        )
    return videos


def fetch_transcript(video_id: str) -> dict:
    api_key = os.environ.get("TRANSCRIPT_API_KEY")
    if not api_key:
        raise AutopilotError("TRANSCRIPT_API_KEY is not set")
    query = urllib.parse.urlencode(
        {
            "video_url": video_id,
            "format": "json",
            "include_timestamp": "true",
            "send_metadata": "true",
            "language": "en",
            "language_fallback": "true",
        }
    )
    req = urllib.request.Request(
        f"{TRANSCRIPT_URL}?{query}", headers={"Authorization": f"Bearer {api_key}", "User-Agent": USER_AGENT}
    )
    data = None
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            break
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                raise TranscriptNotReady(f"No captions yet for {video_id}") from exc
            if (exc.code in (408, 429) or exc.code >= 500) and attempt < 3:
                time.sleep(10 * (attempt + 1))
                continue
            raise AutopilotError(f"TranscriptAPI HTTP {exc.code} for {video_id}") from exc
        except urllib.error.URLError as exc:
            raise AutopilotError(f"TranscriptAPI connection error: {exc.reason}") from exc
    lines = (data or {}).get("transcript") or []
    if not lines:
        raise TranscriptNotReady(f"Empty captions for {video_id}")
    meta = data.get("metadata") or {}
    return {
        "lines": [{"start": int(float(l.get("start") or 0)), "text": l.get("text", "")} for l in lines],
        "length_seconds": int(data.get("length_seconds") or 0),
        "youtube_title": meta.get("title"),
    }


# --------------------------------------------------------------------------- generation

def generate(video: dict, transcript: dict) -> dict:
    import anthropic

    client = anthropic.Anthropic()
    captions = "\n".join(f"[{l['start']}] {l['text']}" for l in transcript["lines"])
    user = (
        f"YouTube title: {transcript.get('youtube_title') or video['title']}\n"
        f"Length: {transcript['length_seconds']} seconds\n"
        f"YouTube description:\n{video.get('description') or '(none)'}\n\n"
        f"Auto captions ([second] text):\n{captions}"
    )
    with client.beta.messages.stream(
        model=os.environ.get("VIDEO_AUTOPILOT_MODEL", "claude-opus-5-5"),
        max_tokens=64000,
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        output_config={"effort": "high", "format": {"type": "json_schema", "schema": OUTPUT_SCHEMA}},
        system=[{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": user}],
    ) as stream:
        message = stream.get_final_message()

    if message.stop_reason == "refusal":
        raise AutopilotError(f"Claude declined {video['youtube_id']}")
    if message.stop_reason == "max_tokens":
        raise AutopilotError(f"Output cut off for {video['youtube_id']}")
    text = next((b.text for b in message.content if b.type == "text"), None)
    if not text:
        raise AutopilotError(f"Empty response for {video['youtube_id']}")
    return json.loads(text)


# --------------------------------------------------------------------------- validation

def _no_em_dash(value):
    if isinstance(value, str):
        return re.sub(r"\s*—\s*", ", ", value).replace("–", "-")
    if isinstance(value, list):
        return [_no_em_dash(v) for v in value]
    if isinstance(value, dict):
        return {k: _no_em_dash(v) for k, v in value.items()}
    return value


def validate(data: dict, length_seconds: int) -> dict:
    """Clean what can be cleaned, raise on anything that would publish a broken page."""
    data = _no_em_dash(data)
    problems = []
    for field in ("title", "meta_title", "meta_description", "teaser", "summary"):
        if not (data.get(field) or "").strip():
            problems.append(f"empty {field}")
    if not 3 <= len(data.get("key_takeaways") or []) <= 9:
        problems.append("key_takeaways count")
    if len(data.get("sections") or []) < 3:
        problems.append("fewer than 3 sections")
    for s in data.get("sections") or []:
        if not s["heading"].strip() or not s["blocks"]:
            problems.append(f"empty section {s['heading']!r}")
    if len(data.get("faq") or []) < 3:
        problems.append("fewer than 3 FAQs")
    for key in ("chapters", "transcript"):
        times = [c["t"] for c in data.get(key) or []]
        if len(times) < 2 or times != sorted(times) or (length_seconds and times[-1] > length_seconds + 5):
            problems.append(f"{key} missing or out of order")
    words = sum(len(b["text"].split()) + sum(len(i.split()) for i in b["items"]) for s in data.get("sections") or [] for b in s["blocks"])
    if words < 500:
        problems.append(f"article too short ({words} words)")
    if problems:
        raise AutopilotError("Invalid content: " + "; ".join(problems))
    return data


# --------------------------------------------------------------------------- save + notify

def best_thumbnail(video_id: str) -> str:
    """maxresdefault exists for custom thumbnails; fall back to hqdefault (always there)."""
    url = f"https://i.ytimg.com/vi/{video_id}/maxresdefault.jpg"
    try:
        req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status == 200:
                return url
    except Exception:
        pass
    return f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"


def save_page(video: dict, transcript: dict, data: dict, out_dir: Path) -> dict:
    existing = {p["slug"]: p for p in load_video_pages()}
    slug = slugify(data["title"])
    same = existing.get(slug)
    if same and same["youtube_id"] != video["youtube_id"]:
        slug = f"{slug}-{video['youtube_id'][:5].lower()}"
    published = (video.get("published") or "")[:10] or date.today().isoformat()
    page = {
        "thumbnail": best_thumbnail(video["youtube_id"]),
        "slug": slug,
        "youtube_id": video["youtube_id"],
        "youtube_title": transcript.get("youtube_title") or video["title"],
        "published": published,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "duration_seconds": transcript["length_seconds"],
        **data,
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{slug}.json"
    path.write_text(json.dumps(page, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    log.info("Wrote %s", path)
    return page


def notify(text: str) -> None:
    hook = os.environ.get("SLACK_WEBHOOK_URL")
    if not hook:
        return
    try:
        req = urllib.request.Request(
            hook, data=json.dumps({"text": text}).encode(), headers={"Content-Type": "application/json"}
        )
        urllib.request.urlopen(req, timeout=15).read()
    except Exception as exc:  # a failed ping must not fail the run
        log.warning("Slack notify failed: %s", exc)


# --------------------------------------------------------------------------- main

def build_one(video: dict, out_dir: Path) -> dict:
    transcript = fetch_transcript(video["youtube_id"])
    if transcript["length_seconds"] and transcript["length_seconds"] < MIN_LONG_SECONDS:
        raise AutopilotError(f"{video['youtube_id']} is {transcript['length_seconds']}s, not a long video")
    for attempt in range(3):
        try:
            raw = generate(video, transcript)
            break
        except AutopilotError:
            raise
        except Exception as exc:  # dropped connection mid-stream: the SDK doesn't retry those
            if attempt == 2:
                raise
            log.warning("Generation for %s failed (%s), retrying", video["youtube_id"], exc)
            time.sleep(20 * (attempt + 1))
    data = validate(raw, transcript["length_seconds"])
    return save_page(video, transcript, data, out_dir)


def run(args) -> int:
    since = date.fromisoformat(os.environ.get("VIDEO_AUTOPILOT_SINCE", "2026-10-26"))
    out_dir = Path(args.out).resolve() if args.out else AUTO_DIR
    known = {p["youtube_id"] for p in load_video_pages()}
    feed = fetch_feed()

    if args.video:
        video = next((v for v in feed if v["youtube_id"] == args.video), None) or {
            "youtube_id": args.video, "title": args.video, "published": "", "description": "", "is_short": False,
        }
        todo = [] if (args.video in known and not args.force) else [video]
        if not todo:
            log.info("%s already has a page (use --force to rebuild)", args.video)
    else:
        todo = [
            v for v in feed
            if not v["is_short"] and v["youtube_id"] not in known and v["published"][:10] >= since.isoformat()
        ]
        todo.sort(key=lambda v: v["published"])

    state = _load_state()
    base = os.environ.get("SITE_BASE_URL", "https://sparksmetrics.com").rstrip("/")
    built = 0
    for video in todo:
        vid = video["youtube_id"]
        entry = state.setdefault(vid, {"attempts": 0})
        if entry.get("attempts", 0) >= MAX_ATTEMPTS and not args.video:
            continue
        if args.dry_run:
            log.info("Would build %s %s", vid, video["title"])
            continue
        if built >= args.limit:
            break
        try:
            page = build_one(video, out_dir)
        except TranscriptNotReady as exc:
            log.info("%s", exc)  # captions can take hours after upload; try again next run
            continue
        except Exception as exc:
            entry["attempts"] = entry.get("attempts", 0) + 1
            entry["last_error"] = str(exc)[:500]
            _save_state(state)
            log.exception("Failed %s", vid)
            if entry["attempts"] >= MAX_ATTEMPTS:
                notify(f":warning: Video page for '{video['title']}' failed {MAX_ATTEMPTS}x: {exc}")
            continue
        state[vid] = {"attempts": entry.get("attempts", 0), "slug": page["slug"], "done": page["generated_at"]}
        _save_state(state)
        built += 1
        notify(f":movie_camera: New video page live: *{page['title']}*\n{base}/videos/{page['slug']}")
    log.info("Done: %d page(s) built, %d candidate(s)", built, len(todo))
    return 0


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--video")
    p.add_argument("--out")
    p.add_argument("--force", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--limit", type=int, default=3)
    return run(p.parse_args())


if __name__ == "__main__":
    sys.exit(main())
