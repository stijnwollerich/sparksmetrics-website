"""Case study autopilot: every winning A/B test in Spark becomes an anonymised page at /ab-tests/<slug>.

Run weekly (systemd timer, deploy/sparksmetrics-case-study-autopilot.*):

    ./venv/bin/python tasks/case_study_autopilot.py

For each Spark experiment marked as a winner it:
 1. checks the test is complete (winning variant, positive lift, visitors, dates, hypothesis, a before and
    an after screenshot). Incomplete tests are skipped and listed in the run summary, so the team knows
    what to fill in; they are picked up automatically once complete.
 2. gets anonymised images: the replica mockups already in Spark, or, if there are none, makes them from
    the real screenshots with OpenAI image edits (fictional brand, generic products, same layout and the
    same change) and saves them back to Spark as replica images.
 3. has Claude check every image it will publish against the real screenshots and the client name:
    no logo, brand name, real product names or photos, and the tested change still visible. Images that
    fail are regenerated (max 3 tries); a test whose images never pass is not published.
 4. has Claude write the case study from Spark's data, checks the text against the same blocklist
    (client name, domain, product names read off the screenshots) and writes <slug>.json + images.

Pages are rebuilt when the test's data in Spark changes. Real screenshots and client names never leave
this script. Delete a JSON file to unpublish; add its experiment id to CASE_STUDY_EXCLUDE to keep it off.

Options: --experiment ID (one test, --force to rebuild), --out DIR (write to app/case_studies to seed),
--dry-run (eligibility report only, nothing paid), --no-spark-upload (don't save replicas to Spark).

Env: SPARK_API_TOKEN, SPARK_API_URL (default https://spark.sparksmetrics.com), OPENAI_API_KEY,
ANTHROPIC_API_KEY, optional SLACK_WEBHOOK_URL, SITE_BASE_URL, CASE_STUDY_EXCLUDE (comma-separated ids).
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import logging
import os
import re
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except ImportError:
    pass

from app.case_studies import AUTO_DIR, load_case_studies  # noqa: E402
from app.video_pages import slugify  # noqa: E402

log = logging.getLogger("case_study_autopilot")

SPARK = (os.environ.get("SPARK_API_URL") or "https://spark.sparksmetrics.com").rstrip("/")
CLAUDE_MODEL = os.environ.get("CASE_STUDY_MODEL", "claude-opus-5-5")
IMAGE_MODEL = os.environ.get("CASE_STUDY_IMAGE_MODEL", "gpt-image-2.6-sunburst")
IMAGE_TRIES = 3
STATE_FILE = ROOT / "instance" / "case_study_autopilot_state.json"
# Blocklists hold client and product names, so they live in instance/ (gitignored), never in the page JSON:
# the website repo is public.
TERMS_FILE = ROOT / "instance" / "case_study_blocklists.json"


def _load_terms() -> dict:
    try:
        return json.loads(TERMS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save_terms(exp_id: int, terms: list[str]) -> None:
    data = _load_terms()
    data[str(exp_id)] = terms
    TERMS_FILE.parent.mkdir(parents=True, exist_ok=True)
    TERMS_FILE.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
FICTIONAL_BRANDS = ["Brightnest", "Kindling & Co", "Fernwell", "Northloom", "Halden", "Marlowe Goods",
                    "Tidepool", "Oakhaven", "Lumen & Leaf", "Westbrook Supply", "Copperline", "Juniper Lane"]


class Skip(Exception):
    """Test isn't ready (missing data or images). Not an error: try again next run."""


class Failed(Exception):
    pass


# --------------------------------------------------------------------------- Spark

def _spark_headers() -> dict:
    token = os.environ.get("SPARK_API_TOKEN")
    if not token:
        raise Failed("SPARK_API_TOKEN is not set")
    return {"X-API-Token": token}


def list_winning_ids() -> list[int]:
    r = requests.get(f"{SPARK}/api/experiments", params={"successful": "true", "limit": 500},
                     headers=_spark_headers(), timeout=30)
    r.raise_for_status()
    return [int(e["id"]) for e in r.json().get("experiments") or []]


def get_experiment(exp_id: int) -> dict:
    r = requests.get(f"{SPARK}/api/experiments/{exp_id}", headers=_spark_headers(), timeout=30)
    r.raise_for_status()
    return r.json()


def fetch_image(path: str) -> bytes | None:
    r = requests.get(f"{SPARK}/api/experiments/image", params={"path": path}, headers=_spark_headers(), timeout=60)
    if r.status_code != 200 or not (r.headers.get("Content-Type") or "").startswith("image/"):
        return None
    return r.content


def first_image(paths: list[dict]) -> tuple[bytes, str] | None:
    for img in paths or []:
        p = (img.get("path") or "").strip()
        if p:
            data = fetch_image(p)
            if data:
                return data, p
    return None


def upload_replicas(exp: dict, uploads: dict[int, bytes]) -> None:
    """Append replica images to arms by index. Every arm is sent (empty = unchanged): Spark drops arms
    that are missing from a PATCH."""
    groups = exp.get("variant_groups") or []
    patch = []
    for i in range(len(groups)):
        if i in uploads:
            patch.append({"replica_image_uploads": [{
                "filename": f"replica-{exp['id']}-{i}.png",
                "content_base64": base64.b64encode(uploads[i]).decode(),
            }]})
        else:
            patch.append({})
    r = requests.patch(f"{SPARK}/api/experiments/{exp['id']}", json={"variant_groups": patch},
                       headers=_spark_headers(), timeout=120)
    if r.status_code >= 300:
        raise Failed(f"Spark PATCH {exp['id']} HTTP {r.status_code}: {r.text[:300]}")
    after = r.json().get("experiment") or get_experiment(exp["id"])
    if len(after.get("variant_groups") or []) != len(groups):
        raise Failed(f"Spark PATCH {exp['id']} changed the number of variants, check it in Spark")


# --------------------------------------------------------------------------- eligibility

def _num(v):
    return float(v) if isinstance(v, (int, float)) else None


def summarize(exp: dict) -> dict:
    """Pull out what a case study needs and list what's missing."""
    groups = exp.get("variant_groups") or []
    control = groups[0] if groups else None
    winner_idx = next((i for i, g in enumerate(groups) if i > 0 and g.get("is_winner")), None)
    winner = groups[winner_idx] if winner_idx is not None else None
    w = winner or {}
    conv = _num(w.get("conv_improvement")) or _num(exp.get("conv_improvement"))
    psv = _num(w.get("psv_improvement")) or _num(exp.get("psv_improvement"))
    aov = _num(w.get("aov_improvement")) if w.get("aov_improvement") is not None else _num(exp.get("aov_improvement"))
    rev = _num(w.get("rev_added")) or _num(exp.get("rev_added"))
    visitors = exp.get("testing_users_count") or sum(int(g.get("testing_users_count") or 0) for g in groups) or None
    start, end = exp.get("start_date"), exp.get("end_date")
    days = None
    missing = []
    if not control or winner is None:
        missing.append("a winning variant (mark the winner in Spark)")
    if not ((conv or 0) > 0 or (psv or 0) > 0):
        missing.append("a positive conversion rate or revenue per visitor lift")
    if not visitors:
        missing.append("the number of visitors in the test")
    try:
        days = (date.fromisoformat(end[:10]) - date.fromisoformat(start[:10])).days
        if days < 7:
            missing.append("start and end dates (the test ran under 7 days or the dates are reversed)")
    except (TypeError, ValueError):
        missing.append("start and end dates")
    if len((exp.get("hypothesis") or "").strip()) < 20:
        missing.append("a hypothesis")
    for label, arm in (("control", control), ("winning variant", winner)):
        if arm and not (arm.get("replica_images") or arm.get("images")):
            missing.append(f"a screenshot of the {label}")
    rev_3m = round(rev * 90 / days) if rev and rev > 0 and days and days >= 7 else None
    return {
        "control": control, "winner": winner, "winner_idx": winner_idx, "missing": missing,
        "results": {
            "conv_improvement": round(conv, 1) if conv is not None else None,
            "psv_improvement": round(psv, 1) if psv is not None else None,
            "aov_improvement": round(aov, 1) if aov is not None else None,
            "rev_added": round(rev) if rev else None,
            "rev_added_3m": rev_3m,
            "visitors": int(visitors) if visitors else None,
            "days": days,
        },
    }


def fingerprint(exp: dict) -> str:
    keys = ("test_name", "page", "hypothesis", "outcome", "learnings", "start_date", "end_date",
            "conv_improvement", "psv_improvement", "aov_improvement", "rev_added", "testing_users_count")
    groups = [{k: g.get(k) for k in ("name", "summary", "is_winner", "conv_improvement", "psv_improvement",
                                       "aov_improvement", "testing_users_count")} for g in exp.get("variant_groups") or []]
    raw = json.dumps({**{k: exp.get(k) for k in keys}, "groups": groups}, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


# --------------------------------------------------------------------------- images

def _png(data: bytes, max_side: int = 1600) -> bytes:
    from PIL import Image

    im = Image.open(io.BytesIO(data)).convert("RGB")
    im.thumbnail((max_side, max_side))
    out = io.BytesIO()
    im.save(out, "PNG")
    return out.getvalue()


def _size_for(data: bytes) -> str:
    from PIL import Image

    w, h = Image.open(io.BytesIO(data)).size
    if h > w * 1.15:
        return "1024x1536"
    if w > h * 1.15:
        return "1536x1024"
    return "1024x1024"


def openai_edit(refs: list[bytes], prompt: str, size: str) -> bytes:
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise Failed("OPENAI_API_KEY is not set")
    files = [("image[]", (f"ref{i}.png", _png(b), "image/png")) for i, b in enumerate(refs)]
    for attempt in range(3):
        r = requests.post("https://api.openai.com/v1/images/edits", headers={"Authorization": f"Bearer {key}"},
                          files=files, timeout=600,
                          data={"model": IMAGE_MODEL, "prompt": prompt, "size": size, "quality": "high"})
        if r.status_code == 200:
            return base64.b64decode(r.json()["data"][0]["b64_json"])
        if r.status_code == 400 and "safety" in r.text:
            raise Skip("OpenAI's image filter refused this screenshot (often photos of people); upload a replica "
                       "mockup in Spark by hand and it will be used")
        if r.status_code in (429, 500, 502, 503) and attempt < 2:
            time.sleep(30 * (attempt + 1))
            continue
        raise Failed(f"OpenAI image edit HTTP {r.status_code}: {r.text[:300]}")
    raise Failed("OpenAI image edit failed")


def control_prompt(brand: str, page: str, feedback: str) -> str:
    return (
        f"Recreate this ecommerce screenshot ({page}) as a clean, realistic UI mockup for a fictional store called "
        f'"{brand}". Keep the exact layout, element order, proportions, spacing, colours, font style and every UI '
        "element (headings, bars, buttons, badges, icons, rows, fields, links, toggles). Make the store unidentifiable: "
        "remove every logo, brand name, watermark, domain and slogan; replace every product name and product photo with "
        "different generic products of a similar kind with new made-up names; change prices slightly and show them in $; "
        "replace every photo (product shots, lifestyle scenes, people, models) with clearly different generic imagery, "
        "different people in different poses and settings; rename any trademarked feature or technology names to generic "
        "descriptions; replace reviewer names and quotes with generic ones; keep all prices in one currency ($). "
        "Remove testing-tool and browser overlays (A/B test preview badges such as 'Visually.io Preview', debug widgets, "
        "cookie banners, chat bubbles). Do not add anything that is not in the original. "
        "All text crisp and readable. Same framing as the screenshot, no device frame."
        + (f" Fix these problems from the previous attempt: {feedback}" if feedback else "")
    )


def winner_prompt(brand: str, page: str, feedback: str) -> str:
    return (
        f'Image 1 is an anonymised mockup of a {page} for the fictional store "{brand}". Image 2 is the redesigned '
        f"version of the same page from the real store. Produce the redesigned page from image 2 for \"{brand}\": "
        "reproduce image 2's layout, element order, styling and every difference from image 1 exactly (new or removed "
        "elements, new labels and copy, changed buttons, moved blocks), but use the fictional products, product photos, "
        "names and prices from image 1. Never reuse a photo from image 2: any photo that is new in image 2 (lifestyle "
        "scenes, people, videos) must be a clearly different generic image. No logos, real brand names, trademarked "
        "feature names, domains or real product names. All text crisp and "
        "readable. Same framing as image 2, no device frame."
        + (f" Fix these problems from the previous attempt: {feedback}" if feedback else "")
    )


IMAGE_CHECK_SCHEMA = {
    "type": "object",
    "properties": {
        "identifying_terms": {"type": "array", "items": {"type": "string"}},
        "control_ok": {"type": "boolean"},
        "winner_ok": {"type": "boolean"},
        "change_preserved": {"type": "boolean"},
        "change_description": {"type": "string"},
        "issues": {"type": "string"},
    },
    "required": ["identifying_terms", "control_ok", "winner_ok", "change_preserved", "change_description", "issues"],
    "additionalProperties": False,
}


def _img_block(data: bytes) -> dict:
    return {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": base64.b64encode(_png(data, 1500)).decode()}}


def _claude_json(system: str, content: list, schema: dict, effort: str = "high") -> dict:
    import anthropic

    client = anthropic.Anthropic()
    for attempt in range(3):
        try:
            with client.beta.messages.stream(
                model=CLAUDE_MODEL, max_tokens=32000, betas=["server-side-fallback-2026-07-01"], fallbacks="default",
                output_config={"effort": effort, "format": {"type": "json_schema", "schema": schema}},
                system=system, messages=[{"role": "user", "content": content}],
            ) as stream:
                msg = stream.get_final_message()
            break
        except Exception as exc:
            if attempt == 2:
                raise
            log.warning("Claude call failed (%s), retrying", exc)
            time.sleep(20 * (attempt + 1))
    if msg.stop_reason in ("refusal", "max_tokens"):
        raise Failed(f"Claude stopped: {msg.stop_reason}")
    text = next((b.text for b in msg.content if b.type == "text"), "")
    return json.loads(text)


def check_images(exp: dict, real_c: bytes, real_w: bytes, anon_c: bytes, anon_w: bytes) -> dict:
    system = (
        "You review anonymised screenshots before an agency publishes them in a public case study. The client must not "
        "be identifiable. You get the real control and the real winning variant from the client's store, then the "
        "anonymised control and anonymised winner meant for publication."
    )
    content = [
        {"type": "text", "text": f"Client name: {exp.get('company_name')}\nClient website: {exp.get('website_domain')}\nPage tested: {exp.get('page')}\nTest: {exp.get('test_name')}\n\nImage 1: real control. Image 2: real winning variant. Image 3: anonymised control. Image 4: anonymised winner."},
        _img_block(real_c), _img_block(real_w), _img_block(anon_c), _img_block(anon_w),
        {"type": "text", "text": (
            "Return:\n- identifying_terms: every brand name, product name, collection name, slogan, domain, person name or other "
            "text visible in images 1 and 2 that is specific to this client and could identify it (exact spelling). Leave out "
            "generic shop copy anyone could use, like 'Checkout', 'Free shipping', 'Customers use for assembly'.\n"
            "- control_ok / winner_ok: true only if that anonymised image shows no logo, brand name, domain, real product name, "
            "recognisable real product photo or other identifying text from images 1-2, and its text is legible and not garbled.\n"
            "- change_preserved: true only if every difference between image 1 and image 2 (layout, added or removed elements, and "
            "changed copy such as new labels, headings and button text) is reproduced between image 3 and image 4. Generic copy "
            "should match the real winner; copy about a real product may be adapted to the fictional product, and small "
            "differences in numbers, prices, percentages or promo amounts are fine.\n- change_description: one sentence, what changed from control to winner.\n"
            "- issues: what to fix, concrete and short (empty if all is fine).")},
    ]
    return _claude_json(system, content, IMAGE_CHECK_SCHEMA)


def build_images(exp: dict, summary: dict, upload: bool) -> dict:
    """Return anonymised control + winner (bytes), the blocklist terms and a description of the change."""
    control, winner = summary["control"], summary["winner"]
    real_c = first_image(control.get("images"))
    real_w = first_image(winner.get("images"))
    rep_c = first_image(control.get("replica_images"))
    rep_w = first_image(winner.get("replica_images"))
    if not (real_c or rep_c) or not (real_w or rep_w):
        raise Skip("a before or after screenshot is missing or can't be downloaded from Spark")
    if not real_c or not real_w:
        # replicas only, nothing to compare with: use them, the text check below still guards the copy
        if rep_c and rep_w:
            log.info("Exp %s: replicas without originals, using them as they are", exp["id"])
            return {"control": rep_c[0], "winner": rep_w[0], "terms": [], "change": "", "generated": False}
        raise Skip("needs both real screenshots to make replicas")

    brand = FICTIONAL_BRANDS[int(exp["id"]) % len(FICTIONAL_BRANDS)]
    page = exp.get("page") or "page"
    anon_c = rep_c[0] if rep_c else None   # replicas already in Spark are kept, never regenerated
    anon_w = rep_w[0] if rep_w else None
    redo_c, redo_w = anon_c is None, anon_w is None
    feedback = ""
    for attempt in range(IMAGE_TRIES):
        if redo_c:
            anon_c = openai_edit([real_c[0]], control_prompt(brand, page, feedback), _size_for(real_c[0]))
            redo_w = not rep_w  # the winner is made from the control, so a new control means a new winner
        if redo_w:
            anon_w = openai_edit([anon_c, real_w[0]], winner_prompt(brand, page, feedback), _size_for(real_w[0]))
        verdict = check_images(exp, real_c[0], real_w[0], anon_c, anon_w)
        log.info("Exp %s image check %d: %s %s", exp["id"], attempt + 1,
                 {k: verdict[k] for k in ("control_ok", "winner_ok", "change_preserved")}, verdict["issues"][:200])
        if verdict["control_ok"] and verdict["winner_ok"] and verdict["change_preserved"]:
            break
        if (not verdict["control_ok"] and rep_c) or (not verdict["winner_ok"] and rep_w):
            raise Skip(f"a replica image already in Spark fails the anonymity check: {verdict['issues']}")
        if not verdict["change_preserved"] and rep_c and rep_w:
            raise Skip(f"the replica images in Spark don't show the tested change: {verdict['issues']}")
        feedback = verdict["issues"]
        redo_c = not verdict["control_ok"]
        redo_w = not rep_w
    else:
        raise Failed(f"replicas failed the check {IMAGE_TRIES}x: {verdict['issues']}")

    if upload:
        uploads = {}
        if not rep_c:
            uploads[0] = anon_c
        if not rep_w:
            uploads[summary["winner_idx"]] = anon_w
        if uploads:
            upload_replicas(exp, uploads)
            log.info("Exp %s: saved %d replica image(s) to Spark", exp["id"], len(uploads))
    return {"control": anon_c, "winner": anon_w, "terms": verdict["identifying_terms"],
            "change": verdict["change_description"], "generated": not (rep_c and rep_w)}


def save_webp(data: bytes, path: Path) -> None:
    from PIL import Image

    im = Image.open(io.BytesIO(data)).convert("RGB")
    im.thumbnail((1200, 1800))
    path.parent.mkdir(parents=True, exist_ok=True)
    im.save(path, "WEBP", quality=86, method=6)


# --------------------------------------------------------------------------- text

def _s():
    return {"type": "string"}


def _arr(items):
    return {"type": "array", "items": items}


def _obj(props):
    return {"type": "object", "properties": props, "required": list(props), "additionalProperties": False}


PAGE_TYPES = ["Product page", "Collection page", "Cart", "Checkout", "Homepage", "Navigation", "Landing page", "Site-wide", "Other"]

TEXT_SCHEMA = _obj({
    "title": _s(), "card_title": _s(), "meta_title": _s(), "meta_description": _s(), "teaser": _s(),
    "industry": _s(), "page_type": {"type": "string", "enum": PAGE_TYPES},
    "summary": _s(),
    "problem": _arr(_s()),
    "hypothesis": _s(),
    "control_label": _s(), "winner_label": _s(),
    "changes": _arr(_s()),
    "why_it_worked": _arr(_s()),
    "takeaways": _arr(_s()),
    "faq": _arr(_obj({"q": _s(), "a": _s()})),
    "tags": _arr(_s()),
})

TEXT_SYSTEM = """You write public A/B test case studies for Sparksmetrics, a CRO agency for D2C Shopify brands. Each one turns a winning test from the agency's records into a page that ranks in Google and gets quoted by AI assistants for searches like "cart drawer A/B test" or "does removing upsells from the cart increase conversion".

The client is anonymous. Never write the client's name, website, product names, collection names, slogans, people's names or anything from the blocklist you are given, not even partly. Describe the client only by a broad category and size-neutral wording ("a hobby kit brand", "a home goods brand"). Do not mention the agency's partners either.

Use only facts from the test record. The numbers block is the truth: you may quote those numbers exactly, never others, never round them differently, never invent revenue, traffic or timing. If the record doesn't say why something happened, reason from the change itself and phrase it as the likely reason.

Voice: Stijn Wollerich, founder, first person plural ("we tested"), plain and practical, short paragraphs. Never use the em dash character. No hype, no "game-changer", no "unlock", no "in today's world", no rhetorical one-line closers.

Return:
- title: H1, search-friendly, names the change and the result, e.g. "Cart Declutter A/B Test: 11% More Conversions for a Hobby Kit Brand" (max ~75 chars).
- card_title: short card label, e.g. "Cart declutter" (max ~35 chars).
- meta_title: max 60 chars. meta_description: 140-155 chars.
- teaser: one sentence for the listing card.
- industry: the broad client category, 2-4 words, lower case.
- page_type: the page tested.
- summary: 2-3 sentences, answer first: what we changed, the result, the main reason. Quotable on its own.
- problem: 1-3 short paragraphs: what was wrong with the original page and how we found it (only what the record supports).
- hypothesis: the hypothesis rewritten in plain words, one or two sentences, "If we..., then..., because...".
- control_label / winner_label: one line each describing the original and the winning version.
- changes: 2-6 bullets, concretely what changed on the page.
- why_it_worked: 2-3 short paragraphs.
- takeaways: 3-5 bullets, how another store can apply this. Each self-contained and actionable.
- faq: 3-5 questions people search about this kind of test, answered in 2-4 sentences from this test and general CRO practice.
- tags: 2-4 from: "Product page", "Collection page", "Cart", "Checkout", "Navigation", "Mobile", "Social proof", "Pricing", "Upsells", "Product media", "Copy", "Layout", "Trust", "Subscriptions".
"""


def write_text(exp: dict, summary: dict, images: dict) -> dict:
    r = summary["results"]
    numbers = {k: v for k, v in {
        "conversion rate change %": r["conv_improvement"], "revenue per visitor change %": r["psv_improvement"],
        "average order value change %": r["aov_improvement"], "visitors in the test": r["visitors"],
        "test length in days": r["days"]}.items() if v is not None}
    arms = []
    for i, g in enumerate(exp.get("variant_groups") or []):
        arms.append(f"- {'Control' if i == 0 else 'Variant'} '{g.get('name')}'{' (WINNER)' if g.get('is_winner') else ''}: "
                    f"{g.get('summary') or ''} | conv {g.get('conv_improvement')}%, rev/visitor {g.get('psv_improvement')}%")
    record = (
        f"Test name: {exp.get('test_name')}\nPage: {exp.get('page')}\nHypothesis: {exp.get('hypothesis')}\n"
        f"Outcome: {exp.get('outcome') or ''}\nLearnings: {exp.get('learnings') or ''}\nVariants:\n" + "\n".join(arms) +
        f"\nWhat changed (seen in the screenshots): {images.get('change') or ''}\n\nNumbers (the only numbers you may use): {json.dumps(numbers)}\n\n"
        f"Blocklist (never write these): {json.dumps(blocklist(exp, images))}"
    )
    content = [
        {"type": "text", "text": "Anonymised screenshots. Image 1: original (control). Image 2: winning variant."},
        _img_block(images["control"]), _img_block(images["winner"]),
        {"type": "text", "text": record},
    ]
    return _claude_json(TEXT_SYSTEM, content, TEXT_SCHEMA)


def blocklist(exp: dict, images: dict) -> list[str]:
    terms = set()
    name = (exp.get("company_name") or "").strip()
    if name:
        terms.add(name)
        terms.add(name.replace(" ", ""))
    dom = (exp.get("website_domain") or "").lower()
    dom = re.sub(r"^https?://", "", dom).split("/")[0].removeprefix("www.")
    if dom:
        terms.add(dom)
        terms.add(dom.split(".")[0])
    if exp.get("visually_client_alias"):
        terms.add(exp["visually_client_alias"])
    for t in images.get("terms") or []:
        t = (t or "").strip()
        if len(t) >= 4:
            terms.add(t)
    return sorted(t for t in terms if len(t) >= 4)


def _no_em_dash(value):
    if isinstance(value, str):
        return re.sub(r"\s*—\s*", ", ", value).replace("–", "-")
    if isinstance(value, list):
        return [_no_em_dash(v) for v in value]
    if isinstance(value, dict):
        return {k: _no_em_dash(v) for k, v in value.items()}
    return value


def validate_text(text: dict, terms: list[str]) -> dict:
    text = _no_em_dash(text)
    blob = json.dumps(text, ensure_ascii=False).lower()
    leaks = [t for t in terms if t.lower() in blob]
    if leaks:
        raise Failed(f"text mentions blocked terms: {leaks}")
    problems = [f for f in ("title", "summary", "meta_description", "hypothesis") if not text.get(f, "").strip()]
    if len(text.get("changes") or []) < 1 or len(text.get("faq") or []) < 2 or len(text.get("takeaways") or []) < 2:
        problems.append("lists too short")
    if problems:
        raise Failed(f"invalid text: {problems}")
    return text


# --------------------------------------------------------------------------- build

def build(exp_id: int, out_dir: Path, existing: dict | None, upload: bool, force: bool) -> dict | None:
    exp = get_experiment(exp_id)
    summary = summarize(exp)
    if summary["missing"]:
        raise Skip("missing " + "; ".join(summary["missing"]))
    fp = fingerprint(exp)
    if existing and existing.get("fingerprint") == fp and not force:
        return None

    stored_terms = _load_terms().get(str(exp_id))
    if existing and not force and stored_terms is not None and (out_dir / "images" / existing["images"]["control"]).exists():
        # data changed but images are done: keep them, rewrite the text (without a stored blocklist we redo the
        # image step instead, which reuses the replicas in Spark and re-reads the identifying terms)
        img_dir = out_dir / "images"
        images = {"control": (img_dir / existing["images"]["control"]).read_bytes(),
                  "winner": (img_dir / existing["images"]["winner"]).read_bytes(),
                  "terms": stored_terms, "change": existing.get("change_seen", "")}
    else:
        images = build_images(exp, summary, upload)
    terms = blocklist(exp, images)
    text = None
    for attempt in range(2):
        try:
            text = validate_text(write_text(exp, summary, images), terms)
            break
        except Failed as exc:
            if attempt == 1:
                raise
            log.warning("Exp %s: %s, rewriting", exp_id, exc)

    slug = existing["slug"] if existing else slugify(re.sub(r"\bA/B\b", "AB", text["title"]))
    taken = {c["slug"] for c in load_case_studies(fresh=True) if int(c["experiment_id"]) != exp_id}
    if slug in taken:
        slug = f"{slug}-{exp_id}"
    img_dir = out_dir / "images"
    names = {"control": f"{slug}-before.webp", "winner": f"{slug}-after.webp"}
    save_webp(images["control"], img_dir / names["control"])
    save_webp(images["winner"], img_dir / names["winner"])
    item = {
        "slug": slug,
        "experiment_id": exp_id,
        "fingerprint": fp,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "start_date": exp.get("start_date"),
        "end_date": exp.get("end_date"),
        "results": summary["results"],
        "images": names,
        "change_seen": images.get("change", ""),
        **text,
    }
    leaks = [t for t in terms if t.lower() in json.dumps(item, ensure_ascii=False).lower()]
    if leaks:
        raise Failed(f"page data mentions blocked terms: {leaks}")
    _save_terms(exp_id, terms)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{slug}.json").write_text(json.dumps(item, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return item


def notify(text: str) -> None:
    hook = os.environ.get("SLACK_WEBHOOK_URL")
    if not hook:
        return
    try:
        requests.post(hook, json={"text": text}, timeout=15)
    except Exception as exc:
        log.warning("Slack notify failed: %s", exc)


def run(args) -> int:
    out_dir = Path(args.out).resolve() if args.out else AUTO_DIR
    exclude = {int(x) for x in re.findall(r"\d+", os.environ.get("CASE_STUDY_EXCLUDE", ""))}
    existing = {int(c["experiment_id"]): c for c in load_case_studies(fresh=True)}
    state = {}
    if STATE_FILE.exists():
        try:
            state = json.loads(STATE_FILE.read_text())
        except ValueError:
            state = {}
    ids = [args.experiment] if args.experiment else [i for i in list_winning_ids() if i not in exclude]
    base = os.environ.get("SITE_BASE_URL", "https://sparksmetrics.com").rstrip("/")
    built, skipped, failed = [], [], []
    for exp_id in ids:
        try:
            if args.dry_run:
                exp = get_experiment(exp_id)
                s = summarize(exp)
                status = "ready" if not s["missing"] else "skip: missing " + "; ".join(s["missing"])
                if exp_id in existing and existing[exp_id].get("fingerprint") == fingerprint(exp):
                    status = "published, up to date"
                log.info("#%s %s: %s", exp_id, exp.get("test_name"), status)
                continue
            st = state.get(str(exp_id)) or {}
            if not args.experiment and st.get("fails", 0) >= 2:
                exp = get_experiment(exp_id)
                if st.get("fingerprint") == fingerprint(exp):
                    raise Skip("replicas failed twice; upload replica mockups in Spark by hand and they will be used "
                               f"(last issue: {st.get('error', '')[:160]})")
            item = build(exp_id, out_dir, existing.get(exp_id), not args.no_spark_upload, args.force)
            state.pop(str(exp_id), None)
            if item:
                built.append(item)
                log.info("Built #%s -> /ab-tests/%s", exp_id, item["slug"])
        except Skip as exc:
            skipped.append((exp_id, str(exc)))
            log.info("Skip #%s: %s", exp_id, exc)
        except Exception as exc:
            failed.append((exp_id, str(exc)[:300]))
            log.exception("Failed #%s", exp_id)
            try:
                fp = fingerprint(get_experiment(exp_id))
            except Exception:
                fp = None
            st = state.get(str(exp_id)) or {}
            fails = st.get("fails", 0) + 1 if st.get("fingerprint") == fp else 1
            state[str(exp_id)] = {"fingerprint": fp, "fails": fails, "error": str(exc)[:500]}
    if not args.dry_run:
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(json.dumps(state, indent=1))
    if built or failed:
        from app.case_studies import is_public

        if is_public():
            lines = [f":trophy: New A/B test case study: *{i['title']}*\n{base}/ab-tests/{i['slug']}" for i in built]
        else:
            lines = [f":trophy: New A/B test case study ready (not public, AB_TESTS_PUBLIC is off): *{i['title']}*" for i in built]
        lines += [f":warning: Case study for test #{i} failed: {e}" for i, e in failed]
        if skipped:
            lines.append("Winning tests waiting for info in Spark:\n" + "\n".join(f"• #{i}: {e}" for i, e in skipped))
        notify("\n".join(lines))
    log.info("Done: %d built, %d skipped, %d failed", len(built), len(skipped), len(failed))
    return 0


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--experiment", type=int)
    p.add_argument("--out")
    p.add_argument("--force", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--no-spark-upload", action="store_true")
    return run(p.parse_args())


if __name__ == "__main__":
    sys.exit(main())
