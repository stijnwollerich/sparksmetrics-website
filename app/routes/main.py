"""Main (public) routes."""
import html
import json
import math
import re
from typing import Any
from pathlib import Path
from datetime import datetime, timezone
from flask import abort, Blueprint, current_app, jsonify, make_response, redirect, render_template, request, Response, url_for, send_file

from app.models import Lead, CroScanReport, db
from app import spark_backend

BREVO_CONTACTS_URL = "https://api.brevo.com/v3/contacts"

main_bp = Blueprint("main", __name__)


@main_bp.context_processor
def inject_enable_gtm():
    """Expose ENABLE_GTM config to templates as ENABLE_GTM."""
    # Default to True so GTM is enabled unless explicitly turned off in config
    return {"ENABLE_GTM": current_app.config.get("ENABLE_GTM", True)}

# Central redirects: (from_paths, target_view_name, status_code). Add new redirects here.
REDIRECTS = [
    (["/cro"], "main.cro", 301),
    (["/30-minute-strategy-session/", "/30-minute-strategy-session"], "main.schedule_a_call", 301),
    (["/case-studies"], "main.results", 301),
]


def _make_redirect_view(target_view: str, code: int):
    """Return a view function that redirects to the given target view with the given status code."""
    def _view():
        return redirect(url_for(target_view), code=code)
    return _view


def _register_redirects():
    """Register all REDIRECTS as URL rules."""
    for paths, target, code in REDIRECTS:
        view = _make_redirect_view(target, code)
        for path in paths:
            endpoint = "redirect_" + path.strip("/").replace("/", "_").replace("-", "_") or "redirect_root"
            main_bp.add_url_rule(path, endpoint=endpoint, view_func=view, methods=["GET"])


_register_redirects()

# Individual case study data (slug -> case dict for case_study.html)
CASE_STUDIES = {
    "global-restaurant-bookings": {
        "meta_title": "62% Increase in Booking Conversions | Sparksmetrics",
        "result_headline": "62% Increase in Booking Conversions",
        "subtitle": "Redesigning key pages turned more visitors into paying guests.",
        "updated_date": "13 October 2025",
        "project_items": [
            ("Industry", "Entertainment"),
            ("Product Type", "Physical Service (Fine-Dining Experience)"),
            ("Website Type", "Custom-Built"),
            ("Testing Platform", "Convert.com"),
            ("Goal", "Increase bookings"),
            ("Duration", "5 months"),
            ("Traffic Volume", "~1M visitors per month"),
        ],
        "challenge": [
            "This global entertainment brand offers immersive fine-dining shows that blend food, theater, and technology. Despite massive social buzz and strong traffic from paid and organic channels, their site wasn't converting as it should.",
            "Visitors loved the concept but were confused by the offer. The value proposition wasn't clear, the booking flow was cluttered with too many options, and social proof—one of the brand's strongest assets—was buried.",
            "The result: high interest, low bookings, and wasted ad spend.",
        ],
        "approach": [
            "We started with data. Session recordings, heatmaps, and analytics revealed where users hesitated and why. Three priorities emerged: simplify the message, remove friction, and make trust visible.",
            "We redesigned the location page around a single promise: an unforgettable dining experience worth sharing. We clarified what the event is, who it's for, and what to expect—backed by social proof and strong CTAs. Next, we restructured the checkout to guide users step by step. Essential elements stayed visible; optional extras were moved deeper into the flow to reduce overwhelm.",
            "Finally, we revamped the homepage, filling it with real guest photos, press mentions, and reviews—emotional proof that built trust before users ever clicked \"Book Now.\"",
        ],
        "tests": [
            "Each change was validated through controlled A/B testing. The redesigned location page was tested against the original version using a 50/50 traffic split, with clear primary goals: booking start and completed transactions.",
            "The checkout improvements were tested separately to measure drop-off reduction, and the homepage enhancements were validated through behavior metrics—engagement rate, time on page, and click-through to booking. All experiments ran until full statistical confidence was reached, ensuring the uplift wasn't by chance.",
        ],
        "result_metric": "+62.48% booking start conversions (100% statistical confidence)",
        "result": [
            "The redesigned location page achieved a +62.48% increase in booking start conversions, with 100% statistical confidence.",
            "Checkout completion rates improved significantly, and bounce rates on the homepage dropped.",
            "No new traffic. No extra ad spend. Just a refined user journey that helped people say \"yes\" faster.",
            "By clarifying the offer and removing hesitation points, the brand turned existing visitors into paying guests—unlocking more revenue from the traffic they already had.",
        ],
        "card_title": "Global Dining & Entertainment Brand",
        "card_metrics": [{"value": "8.53x", "label": "Return on Investment"}, {"value": "+63%", "label": "Conversion Rate"}],
        "main_image": "images/location-page.jpg",
        "results_image": "images/test-results.png",
        "gallery_images": [
            {"src": "images/location-page-figma.jpg", "caption": "Location page — Figma design"},
            {"src": "images/screenshot-15-29.png", "caption": "Test setup"},
            {"src": "images/screenshot-15-43.png", "caption": "Test results detail"},
        ],
    },
    "shopify-premium-home-wellness-brand": {
        "meta_title": "22% Lift in Conversion Rate for a Shopify Premium Home-Wellness Brand | Sparksmetrics",
        "result_headline": "22% Lift in Conversion Rate for a Shopify Premium Home-Wellness Brand",
        "subtitle": "Data-backed PDP experiments improved revenue per visitor.",
        "updated_date": "13 October 2025",
        "project_items": [
            ("Industry", "Home wellness brand"),
            ("Product Type", "Physical product"),
            ("Website Type", "Shopify"),
            ("Testing Platform", "Visually"),
            ("Goal", "Increase revenue per session"),
            ("Duration", "6 months"),
            ("Traffic Volume", "~1M visitors per month"),
        ],
        "challenge": [
            "The site was well-designed and functioned smoothly, but performance had plateaued. The low-hanging fruit was already gone.",
            "To move the needle, we needed to understand why visitors hesitated, what details mattered most to them, and how to guide them toward higher-value behaviors—not just a single purchase, but ongoing subscription engagement.",
            "Our challenge was twofold: (1) Identify micro-optimizations that could make a measurable difference on a mature site. (2) Ensure every improvement supported higher LTV, not just AOV or CR.",
        ],
        "approach": [
            "We collaborated closely with the brand's designer and developer to plan and execute a series of high-impact A/B tests using Visually.io. Our process combined data analysis, UX research, and customer insight to form clear hypotheses for each test.",
            "We mapped the entire user journey—from browsing to checkout—and identified opportunities to: strengthen the visual hierarchy of subscription options; simplify decision-making on the PDP; bring trust and social proof closer to conversion moments; improve content flow above and below the fold.",
            "Every idea was implemented with design precision and technical accuracy, ensuring visual consistency while maintaining site speed and stability.",
        ],
        "tests": [
            "Over several months, we tested multiple sections of the site: Collection Page (clarified product positioning and improved filter hierarchy); Product Pages above and below the fold (refined messaging, restructured variants, repositioned testimonials); Add-to-Cart options (simplified subscriptions, made recurring benefits more prominent); Checkout testimonials (added persuasive elements to reduce last-minute drop-offs).",
            "Not every variant won—that's exactly how we validated what truly influenced conversions and retention. The most successful tests showed +22.5% to +10% lifts in conversion rate, with corresponding increases in revenue per visitor and subscription adoption.",
        ],
        "result_metric": "+10% to +22.5% conversion lift on product pages",
        "result": [
            "The experiments confirmed a strong return on testing investment: +10%–+22.5% conversion lift on the product pages; increased subscription selection and retention rates across tested products.",
            "By focusing on behavior-driven design and LTV-oriented testing, we helped the brand convert more visitors and create longer-lasting customer relationships—without increasing ad spend.",
        ],
        "card_title": "Shopify Subscription-Based Wellness Brand",
        "card_metrics": [{"value": "+6%", "label": "Subscriptions"}, {"value": "+22%", "label": "Conversion Rate"}, {"value": "+5%", "label": "Average Order Value"}],
        "main_image": "images/wellness-main.jpg",
        "results_images": [
            {"src": "images/wellness-results-1.png", "caption": "A/B test results"},
            {"src": "images/wellness-results-2.png", "caption": "Test results detail"},
        ],
        "gallery_images": [
            {"src": "images/wellness-figma.jpg", "caption": "Figma design"},
            {"src": "images/wellness-screenshot-1.png", "caption": "Test setup"},
            {"src": "images/wellness-screenshot-2.png", "caption": "Screenshot"},
            {"src": "images/wellness-screenshot-3.png", "caption": "Screenshot"},
        ],
    },
    "ai-brand-redesign": {
        "meta_title": "Redesigning an AI Brand for Higher Credibility and Lead Growth | Sparksmetrics",
        "result_headline": "Redesigning an AI Brand for Higher Credibility and Lead Growth",
        "subtitle": "Elevated trust, clarity, and conversions.",
        "updated_date": "13 October 2025",
        "project_items": [
            ("Client", "AI technology company"),
            ("Website Type", "WordPress"),
            ("Goal", "Generate more qualified leads"),
        ],
        "challenge": [
            "The existing website faced two main challenges: perception and structure.",
            "From a visual standpoint, the design felt dated and failed to convey the sophistication of the company's technology. Structurally, the site lacked a logical flow from problem to solution to proof, making it difficult for visitors to understand the value proposition and take action.",
            "As a result, potential clients were leaving without engaging further—not because of low-quality traffic, but because the experience did not inspire confidence.",
        ],
        "approach": [
            "We focused on three key pillars: clarity, credibility, and conversion intent.",
            "The new structure guided visitors through a clear and persuasive journey: a focused value proposition above the fold (outcomes rather than features); content reorganized to present the problem, the solution, and the evidence that builds trust; a refined visual language, cohesive typography, and modern layout that convey confidence and professionalism.",
            "Every design and copy element worked together to build trust and encourage meaningful conversions.",
        ],
        "tests": [
            "Full redesign and launch—no A/B tests; the new site replaced the existing experience.",
        ],
        "result_metric": "Higher credibility, stronger engagement, increased lead generation",
        "result": [
            "The redesign fundamentally changed how the brand is perceived online. The new website presents a modern, credible, and trustworthy image aligned with the company's position in the AI sector.",
            "Through improved storytelling, structure, and visual execution, the site now drives stronger engagement, increased lead generation, and a higher level of confidence among prospective clients.",
        ],
        "card_title": "AI Brand Redesign for Lead Growth",
        "card_metrics": [],
        "main_image": "images/ai-main.jpg",
        "gallery_images": [
            {"src": "images/ai-figma-1.jpg", "caption": "Figma design"},
            {"src": "images/ai-figma-2.jpg", "caption": "Figma design"},
            {"src": "images/ai-figma-3.jpg", "caption": "Figma design"},
            {"src": "images/ai-figma-4.jpg", "caption": "Figma design"},
        ],
    },
    "shopify-bidet-brand": {
        "meta_title": "20% Increase in Conversion Rate for a Shopify Home-Essentials Brand | Sparksmetrics",
        "result_headline": "20% Increase in Conversion Rate for a Shopify Home-Essentials Brand",
        "subtitle": "Redesigning the product page and homepage to improve engagement.",
        "updated_date": "13 October 2025",
        "project_items": [
            ("Client", "Shopify home-essentials brand (bidet products)"),
            ("Website Type", "Shopify"),
            ("Testing Platform", "Visually.io"),
            ("Goal", "Increase add-to-cart rate and product discovery"),
        ],
        "challenge": [
            "The original website was functional and visually appealing but underperforming in two areas: user engagement and conversion clarity. The homepage did not effectively drive visitors toward products, and the product detail page lacked focus above the fold—forcing users to scroll before understanding why the product was worth purchasing.",
            "Our challenge was to improve how quickly visitors understood the value proposition and how easily they could act on it.",
        ],
        "approach": [
            "We focused on two high-impact areas: the homepage and the product detail page (PDP).",
            "On the homepage, we restructured content to prioritize product discovery—surfacing key categories earlier and aligning the visual hierarchy around the main call-to-action. On the PDP, we redesigned the above-the-fold section to communicate trust and utility faster: simplified messaging, highlighted top differentiators (universal fit, savings, DIY installation), and improved the visual balance between product imagery, reviews, and purchase options.",
            "All tests were implemented and measured on Shopify using Visually.io in close collaboration with the brand's design and development teams.",
        ],
        "tests": [
            "A/B tests on the redesigned PDP and homepage—measured for conversion rate, add-to-cart rate, and revenue per visitor.",
        ],
        "result_metric": "+20% conversion rate (99% confidence); revenue per visitor and add-to-cart up",
        "result": [
            "The redesigned PDP achieved a +20% increase in conversion rate, with a 99% confidence level. Revenue per visitor and add-to-cart rates followed a similar upward trend.",
            "By combining design clarity with data-driven experimentation, we helped the brand turn more visitors into buyers—improving efficiency and revenue without additional ad spend.",
        ],
        "card_title": "Leading Shopify Home-Essentials Brand",
        "card_metrics": [{"value": "+20%", "label": "Conversion Rate"}, {"value": "+15%", "label": "Per Session Value"}],
        "main_image": "images/bidet-main.jpg",
        "gallery_images": [
            {"src": "images/bidet-gallery.jpg", "caption": "Product page design"},
        ],
    },
    "global-tour-brand": {
        "meta_title": "Improving Booking Experience for a Global Tour Brand | Sparksmetrics",
        "result_headline": "Improving Booking Experience for a Global Tour Brand",
        "subtitle": "A custom-built redesign focused on clarity, simplicity, and user confidence.",
        "updated_date": "13 October 2025",
        "project_items": [
            ("Client", "Global tour operator (travel & culinary experiences)"),
            ("Website Type", "Custom-built booking platform"),
            ("Goal", "Increase booking rate; make process intuitive, fast, trustworthy"),
        ],
        "challenge": [
            "While the platform was technically robust, the user journey was complex. Visitors struggled to understand key booking details—tour availability, pricing options, and what to expect at each step.",
            "The design lacked visual hierarchy, and the booking widget felt heavy, creating friction that discouraged users from completing reservations. We needed to create a flow that reduced decision fatigue and built confidence in booking directly through the site.",
        ],
        "approach": [
            "We began by mapping the full user journey from discovery to confirmation, identifying where users hesitated or dropped off. Our approach focused on three principles: Clarity (simplified information architecture so visitors immediately understood the offer, inclusions, and next steps); Trust (highlighted social proof—reviews, partner logos, booking guarantees—near action points); Ease of Use (redesigned the PDP booking module for better flow on desktop and mobile, making date, guest, and location selection frictionless).",
            "Every design decision was guided by data from prior analytics and user behavior insights, ensuring we addressed genuine pain points rather than assumptions.",
        ],
        "tests": [
            "Redesign and launch of the PDP booking experience—no A/B test metrics specified; focus on clarity, trust, and ease of use.",
        ],
        "result_metric": "Cleaner, more confident booking experience aligned with global reputation",
        "result": [
            "The new design delivers a cleaner, more confident booking experience that aligns with the brand's global reputation.",
            "By improving clarity, reducing friction, and reinforcing trust at every step, the new PDPs are set to convert a higher share of visitors into paying guests—particularly on high-intent traffic from search and retargeting campaigns.",
        ],
        "card_title": "Global Food Tour Brand",
        "card_metrics": [],
        "main_image": "images/tour-main.jpg",
        "gallery_images": [
            {"src": "images/tour-gallery-1.jpg", "caption": "Booking experience"},
            {"src": "images/tour-gallery-2.jpg", "caption": "PDP design"},
        ],
    },
    "national-fitness-franchise": {
        "meta_title": "High-Conversion Product Pages for a National Kids Fitness Franchise | Sparksmetrics",
        "result_headline": "Designing High-Conversion Product Pages for a National Kids Fitness Franchise",
        "subtitle": "A custom-built solution to showcase safety, trust, and fun.",
        "updated_date": "13 October 2025",
        "project_items": [
            ("Client", "U.S. franchise — children's fitness and movement programs"),
            ("Scope", "Design and custom development of product pages"),
            ("Goal", "Drive class bookings; convert parents into trial sign-ups"),
        ],
        "challenge": [
            "The existing site successfully explained the concept but did not effectively convert visitors into bookings. Parents wanted reassurance that classes were safe, structured, and taught by professionals—but the original content hierarchy buried unique benefits and left key questions unanswered.",
            "Our challenge was to redesign the experience to clearly highlight the program's USPs: certified instructors, small class sizes, expert safety standards, and developmental benefits—all while keeping the layout engaging and easy to navigate.",
        ],
        "approach": [
            "We focused on clarity, credibility, and emotional appeal. Each new product page was designed to mirror the excitement of the in-person experience while addressing parents' core concerns: a clear above-the-fold section with strong visuals, age group targeting, and direct CTAs; content structured around benefit-driven storytelling (safety, learning, fun); visual proof points such as ratings, parent testimonials, and instructor credentials; a warm, energetic color palette and photography consistent with the brand's family-oriented image.",
            "The pages were fully custom-built, optimized for scalability, and integrated with the franchise's booking system to streamline sign-ups.",
        ],
        "tests": [
            "Custom design and build; pages launched to support trial sign-ups and franchise replication.",
        ],
        "result_metric": "Trusted national leader in kids' fitness; stronger engagement, more trial requests",
        "result": [
            "The new design positions the brand as a trusted national leader in kids' fitness, balancing professionalism with playfulness.",
            "Parents now understand what makes the program unique within seconds—leading to stronger engagement, more trial requests, and higher conversion potential across all franchise locations.",
        ],
        "card_title": "USA National Kids Fitness Franchise",
        "card_metrics": [],
        "main_image": "images/fitness-main.jpg",
        "gallery_images": [
            {"src": "images/fitness-gallery-1.jpg", "caption": "Product page design"},
            {"src": "images/fitness-gallery-2.jpg", "caption": "Figma design"},
            {"src": "images/fitness-gallery-3.jpg", "caption": "Figma design"},
        ],
    },
}

# Display order for case study cards (homepage + results). Add new slugs here to show everywhere.
CASE_STUDY_ORDER = [
    "global-restaurant-bookings",
    "shopify-premium-home-wellness-brand",
    "shopify-bidet-brand",
    "ai-brand-redesign",
    "global-tour-brand",
    "national-fitness-franchise",
]

def _load_blog_posts() -> list[dict]:
    """Load blog posts metadata from app/blog_posts.json (cron-friendly)."""
    path = Path(__file__).resolve().parents[1] / "blog_posts.json"
    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
        posts = data.get("posts") if isinstance(data, dict) else data
        return list(posts or [])
    except Exception:
        return []


def _scan_blog_templates() -> list[dict]:
    """Scan app/templates/blog/ for templates and build a lightweight posts list.
    This allows the blog index to reflect files in the templates/blog folder automatically.
    """
    tmpl_dir = Path(__file__).resolve().parents[1] / "templates" / "blog"
    if not tmpl_dir.exists():
        return []
    posts: list[dict] = []
    # Load any existing metadata from app/blog_posts.json so we can prefer explicit titles/descriptions
    metadata_by_slug = {}
    try:
        for p in _load_blog_posts():
            if isinstance(p, dict) and p.get("slug"):
                metadata_by_slug[p["slug"]] = p
    except Exception:
        metadata_by_slug = {}
    # Build a reverse map from known video_id -> slug so templates can be renamed
    video_id_to_slug = {
        p.get("video_id"): slug for slug, p in metadata_by_slug.items() if p.get("video_id")
    }
    for f in sorted(tmpl_dir.glob("*.html"), key=lambda p: p.name, reverse=True):
        name = f.name
        # Derive slug: remove leading blog_ if present, and extension
        slug = name
        if slug.startswith("blog_"):
            slug = slug[len("blog_") :]
        slug = slug.rsplit(".html", 1)[0]

        text = f.read_text(encoding="utf-8", errors="ignore")
        # If the template contains an embedded YouTube ID that matches metadata, map this file to that slug.
        m_vid = re.search(r"(?:youtube\\.com/embed/|youtu\\.be/)([A-Za-z0-9_-]{5,20})", text)
        if m_vid:
            found_vid = m_vid.group(1)
            mapped = video_id_to_slug.get(found_vid)
            if mapped:
                # Use the canonical slug from blog_posts.json so URLs remain stable
                slug = mapped
        # Try to extract a sensible title: first <h1> or <h2>, else filename
        m = re.search(r"<h1[^>]*>(.*?)</h1>", text, flags=re.I | re.S)
        if not m:
            m = re.search(r"<h2[^>]*>(.*?)</h2>", text, flags=re.I | re.S)
        raw_title = re.sub(r"<[^>]+>", "", m.group(1)).strip() if m else ""
        # If the extracted title looks like a template variable, treat it as missing
        extracted_title = None if (not raw_title or re.search(r"\{\{\s*post\.|\{\{|\{%\s", raw_title)) else raw_title
        # Prefer explicit metadata from blog_posts.json when available, otherwise use extracted title or filename
        title = (
            metadata_by_slug.get(slug, {}).get("title")
            or extracted_title
            or slug.replace("-", " ").replace("_", " ").title()
        )
        # Extract first paragraph as description, but avoid template placeholders
        m2 = re.search(r"<p[^>]*>(.*?)</p>", text, flags=re.I | re.S)
        description_raw = re.sub(r"<[^>]+>", " ", (m2.group(1) or "")).strip() if m2 else ""
        extracted_description = None if (not description_raw or re.search(r"\{\{|\{%\s", description_raw)) else description_raw
        description = metadata_by_slug.get(slug, {}).get("description") or extracted_description or (title + " — insights and examples.")
        # published date from file mtime
        try:
            mtime = f.stat().st_mtime
            published = datetime.fromtimestamp(mtime).strftime("%d %b %Y")
        except Exception:
            published = datetime.now(timezone.utc).strftime("%d %b %Y")
        # simple reading time estimate (200 wpm)
        words = len(re.findall(r"\w+", re.sub(r"<[^>]+>", " ", text)))
        minutes = max(1, int(round(words / 200.0)))
        reading_time = f"{minutes} min read"

        post = {
            "slug": slug,
            "title": title,
            "description": description[:200],
            "published_date": published,
            "updated_date": published,
            "reading_time": reading_time,
            "category": "CRO",
            "template": f"blog/{name}",
            # include any explicit video_id or youtube_url from metadata so templates can use them
            **({"video_id": metadata_by_slug[slug].get("video_id")} if slug in metadata_by_slug and metadata_by_slug[slug].get("video_id") else {}),
            **({"youtube_url": metadata_by_slug[slug].get("youtube_url")} if slug in metadata_by_slug and metadata_by_slug[slug].get("youtube_url") else {}),
            **({"thumbnail": metadata_by_slug[slug]["thumbnail"]} if slug in metadata_by_slug and metadata_by_slug[slug].get("thumbnail") else {}),
        }
        posts.append(post)
    return posts


# Blog posts (no DB): one HTML template per post. Metadata lives in app/blog_posts.json.
BLOG_POSTS: list[dict] = _load_blog_posts()


@main_bp.route("/")
def index():
    """Home page — CRO landing (light theme)."""
    return render_template("landing_pages/landing_alt.html")


@main_bp.route("/favicon.ico")
def favicon():
    """Redirect to SVG favicon so browsers that request .ico get the icon."""
    return redirect(url_for("static", filename="favicon.svg"))


@main_bp.route("/conversion-rate-optimization")
def cro():
    """CRO (Conversion Rate Optimization) service landing."""
    return render_template("cro.html")


@main_bp.route("/13-actionable-conversion-rate-optimization-strategies-ebook/")
def cro_ebook():
    """CRO ebook / free report landing page."""
    return render_template("cro_ebook.html")


@main_bp.route("/schedule-a-call/")
def schedule_a_call():
    """Schedule a call / booking page."""
    return render_template("schedule_a_call.html")


# Personal email domains we do not accept for CRO scan (company/work email only).
PERSONAL_EMAIL_DOMAINS = frozenset({
    "gmail.com", "googlemail.com", "yahoo.com", "yahoo.co.uk", "yahoo.fr", "outlook.com",
    "hotmail.com", "hotmail.co.uk", "live.com", "msn.com", "icloud.com", "me.com", "mac.com",
    "aol.com", "protonmail.com", "proton.me", "mail.com", "zoho.com", "gmx.com", "gmx.net",
    "yandex.com", "inbox.com", "mail.ru", "tutanota.com", "fastmail.com", "hey.com",
})


def _is_personal_email_domain(email: str) -> bool:
    """Return True if email is from a known personal/free provider (not company)."""
    if not email or "@" not in email:
        return False
    domain = email.split("@", 1)[1].strip().lower()
    return domain in PERSONAL_EMAIL_DOMAINS


@main_bp.route("/thank-you/")
@main_bp.route("/thank-you")
def thank_you():
    """Thank you / VSL page after form submit — no header/footer, Calendly + social proof."""
    from_param = request.args.get("from", "").strip()
    return render_template("thank_you.html", from_param=from_param)


# --- CRO Scan (lead gen, noindex) ---
def _normalize_shopify_url(raw: str) -> str | None:
    """Extract and normalize a store URL for validation. Returns None if unparseable."""
    raw = (raw or "").strip()
    if not raw:
        return None
    raw = raw.replace(" ", "")
    if not raw.startswith(("http://", "https://")):
        raw = "https://" + raw
    try:
        from urllib.parse import urlparse
        p = urlparse(raw)
        if not p.netloc or not p.scheme:
            return None
        # Allow both custom domains and myshopify.com
        return f"{p.scheme}://{p.netloc.lower()}"
    except Exception:
        return None


@main_bp.route("/cro-scan/", methods=["GET"])
@main_bp.route("/cro-scan", methods=["GET"])
def cro_scan_landing():
    """CRO scan lead-gen landing (noindex). Single field: Shopify store URL."""
    submissions_today = _cro_scan_submissions_today()
    return render_template("landing_pages/cro_scan_landing.html", submissions_today=submissions_today)


def _normalize_locale_number_string(raw: str) -> str:
    """Allow `2.5` or `2,5` (decimal comma); `250.000` / `250,000` thousands; strip `$`."""
    s = (raw or "").strip().replace("$", "").replace("\u00a0", "")
    if not s:
        return ""
    s = re.sub(r"\s+", "", s)
    if re.fullmatch(r"\d+,\d{1,2}", s):
        return s.replace(",", ".")
    if re.fullmatch(r"\d{1,3}(\.\d{3})+", s):
        return s.replace(".", "")
    if re.fullmatch(r"\d{1,3}(,\d{3})+", s):
        return s.replace(",", "")
    return s.replace(",", "")


def _parse_usd_amount(raw) -> float | None:
    """Parse a user-supplied dollar amount; returns None if missing or invalid."""
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        if isinstance(raw, bool):
            return None
        v = float(raw)
        return v if math.isfinite(v) and v >= 0 else None
    s = _normalize_locale_number_string(str(raw))
    if not s:
        return None
    try:
        v = float(s)
    except ValueError:
        return None
    if not math.isfinite(v) or v < 0:
        return None
    return v


def _parse_positive_int(raw) -> int | None:
    if raw is None or raw == "":
        return None
    if isinstance(raw, bool):
        return None
    if isinstance(raw, int):
        return raw if raw > 0 else None
    if isinstance(raw, float):
        if not math.isfinite(raw) or raw <= 0:
            return None
        return int(round(raw))
    s = _normalize_locale_number_string(str(raw))
    if not s:
        return None
    try:
        v = int(float(s))
    except ValueError:
        return None
    return v if v > 0 else None


def _parse_cvr_percent(raw) -> float | None:
    """Parse conversion rate as percent (e.g. 2.5 or 2,5 for 2.5%)."""
    v = _parse_usd_amount(raw)
    if v is None or v <= 0 or v > 100:
        return None
    return float(v)


def _cro_plan_for_monthly_orders(transactions_pm: int) -> dict[str, Any]:
    """Published CRO program tier by monthly order volume (Sparksmetrics pricing)."""
    t = int(transactions_pm)
    if t < 3000:
        return {
            "slug": "standard",
            "name": "Standard",
            "price_usd": 3_280.0,
            "roi_guarantee_label": "1x",
            "orders_band": "<3,000 orders/mo",
            "features": [
                "Fix biggest leaks",
                "Limited funnel coverage",
                "Slower testing speed",
                "Design, development, and copywriting",
                "Low parallel testing",
            ],
        }
    if t <= 8_000:
        return {
            "slug": "growth",
            "name": "Growth",
            "price_usd": 4_520.0,
            "roi_guarantee_label": "2x",
            "orders_band": "3,000–8,000 orders/mo",
            "features": [
                "Optimize key funnel stages",
                "More test coverage",
                "Faster testing speed",
                "Design, development, and copywriting",
                "Medium parallel testing",
            ],
        }
    return {
        "slug": "full_stack",
        "name": "Full-Stack",
        "price_usd": 6_880.0,
        "roi_guarantee_label": "3x",
        "orders_band": ">8,000 orders/mo",
        "features": [
            "Optimize entire customer journey",
            "Maximum test coverage",
            "Highest testing speed",
            "Design, development, and copywriting",
            "High parallel testing",
        ],
    }


def _compute_cro_cost_roi_snapshot(monthly_revenue_usd: float, transactions_pm: int) -> dict[str, Any]:
    """
    Illustrative planning numbers for paid-ad landing pages (not a quote).
    Uplift: internal illustration from revenue (not shown as a fixed % on-page).
    Program fee: published tier from monthly order volume.
    """
    r = max(0.0, float(monthly_revenue_usd))
    monthly_uplift = r * 0.15
    annual_uplift = monthly_uplift * 12.0
    plan = _cro_plan_for_monthly_orders(int(transactions_pm))
    fee = float(plan["price_usd"])
    roi_monthly = (monthly_uplift / fee) if fee else 0.0
    return {
        "monthly_revenue_usd": r,
        "monthly_uplift_usd": monthly_uplift,
        "annual_uplift_usd": annual_uplift,
        "retainer_low_usd": fee,
        "retainer_high_usd": fee,
        "retainer_mid_usd": fee,
        "roi_monthly": roi_monthly,
        "plan_slug": plan["slug"],
        "plan_name": plan["name"],
        "plan_roi_guarantee_label": plan["roi_guarantee_label"],
        "plan_orders_band": plan["orders_band"],
    }


def _cro_cost_roi_business_stage_line(
    *,
    monthly_revenue_usd: float,
    monthly_ad_spend_usd: float | None,
    snap: dict[str, Any],
    transactions_pm: int | None = None,
    cvr_percent: float | None = None,
    aov_usd: float | None = None,
) -> str:
    """Compact snapshot for Lead.business_stage (max 120 chars in DB)."""

    def k(x: float) -> str:
        ax = abs(x)
        if ax >= 1_000_000:
            return f"{x / 1_000_000:.1f}M".replace(".0M", "M")
        if ax >= 1_000:
            return f"{round(x / 1_000)}k"
        return str(int(round(x)))

    parts: list[str] = []
    if transactions_pm is not None and transactions_pm > 0:
        parts.append(f"ord/mo~{transactions_pm}")
    if cvr_percent is not None and cvr_percent > 0:
        cvr_s = f"{cvr_percent:.2f}".rstrip("0").rstrip(".")
        parts.append(f"cvr{cvr_s}%")
    if aov_usd is not None and aov_usd > 0:
        parts.append(f"aov${k(aov_usd)}")
    fee_i = int(round(float(snap.get("retainer_mid_usd") or 0)))
    slug = (snap.get("plan_slug") or "")[:12]
    guar = snap.get("plan_roi_guarantee_label") or ""
    parts.extend(
        [
            f"rev~${k(monthly_revenue_usd)}",
            f"illust≈${k(snap['monthly_uplift_usd'])}/mo",
            f"{slug}|${fee_i}|{guar}",
            f"ROI~{snap['roi_monthly']:.1f}x",
        ]
    )
    if monthly_ad_spend_usd and monthly_ad_spend_usd > 0:
        parts.append(f"ads${k(monthly_ad_spend_usd)}")
    s = " | ".join(parts)
    return s[:120]


def _send_cro_cost_roi_results_email(
    *,
    to_email: str,
    fname: str,
    monthly_revenue_usd: float,
    transactions_pm: int,
    cvr_percent: float,
    website_url: str,
    snap: dict[str, Any],
) -> None:
    """Send calculator follow-up via Brevo transactional API. No-op if BREVO_SENDER_EMAIL unset."""
    sender = (current_app.config.get("BREVO_SENDER_EMAIL") or "").strip()
    sender_name = (current_app.config.get("BREVO_SENDER_NAME") or "Sparksmetrics").strip()
    if not sender:
        current_app.logger.info("CRO cost ROI email skipped: BREVO_SENDER_EMAIL not set")
        return

    from app.cro_nurture.services.brevo_send import send_transactional_html
    from app.cro_nurture.services.dispatch import (
        _closing_and_signature_html,
        _signature_links_row_html,
    )

    plan_name = str(snap.get("plan_name") or "")
    fee = float(snap.get("retainer_mid_usd") or 0.0)
    lift = float(snap.get("monthly_uplift_usd") or 0.0)
    guar = str(snap.get("plan_roi_guarantee_label") or "")
    roi_m = float(snap.get("roi_monthly") or 0.0)
    if roi_m < 0.1:
        roi_disp = "<0.1×"
    else:
        s_roi = f"{roi_m:.1f}"
        if s_roi.endswith(".0"):
            s_roi = s_roi[:-2]
        roi_disp = s_roi + "×"

    safe_fname = html.escape(fname)
    safe_url = html.escape(website_url)
    esc_plan = html.escape(plan_name)
    esc_roi = html.escape(roi_disp)
    results_url = url_for("main.results", _external=True)
    schedule_url = url_for("main.schedule_a_call", _external=True)
    esc_results = html.escape(results_url, quote=True)
    esc_schedule = html.escape(schedule_url, quote=True)

    guar_plain = guar.strip() or "published by tier (I can spell out what applies on a call)"
    text_body = "\n".join(
        [
            f"Hi {fname},",
            "",
            "Thanks for running our CRO cost vs ROI calculator. I pulled together the snapshot from what you entered so you have it in one place.",
            "",
            f"You shared {website_url}, about ${monthly_revenue_usd:,.0f} in monthly revenue, roughly {transactions_pm:,} orders per month, and about {cvr_percent:g}% CVR.",
            "",
            f"Framed the same way as on the calculator: with a monthly investment of about ${fee:,.0f} on the {plan_name} tier, the illustration implies about ${lift:,.0f} in monthly revenue uplift "
            f"(a planning figure from the model, not a promise). That works out to roughly {roi_disp} ROI against that monthly fee on those same assumptions.",
            f"Our guarantee on qualifying work for this tier is {guar_plain} as we publish it—happy to explain what that covers in plain language.",
            "",
            "When we work with a store, the programme covers analytics, design, and development together so we can go from insight to shipped experiments without hand-offs stalling the work.",
            "",
            "If you want a second pair of eyes on whether this kind of programme is a fit, the clearest next step is a free strategy session. No pitch deck—just your site, your goals, and a practical look at where we would start.",
            "",
            f"Schedule a free strategy session: {schedule_url}",
            "",
            f"If you would rather browse first, here is our results page with case studies: {results_url}",
            "",
            "Reply to this email if something in the snapshot does not line up with how you think about the business—we are happy to sanity-check it.",
            "",
            "If there's anything I can help with, let me know.",
            "",
            "Thanks,",
            "Stijn Wollerich",
            "sparksmetrics.com · Book a call: https://sparksmetrics.com/schedule-a-call/",
        ]
    )

    esc_guar_body = html.escape(guar_plain)
    html_core = f"""<!DOCTYPE html><html><body style="font-family:system-ui,-apple-system,sans-serif;line-height:1.6;color:#111;max-width:36rem;">
<p>Hi {safe_fname},</p>
<p>Thanks for running our CRO cost vs ROI calculator. I pulled together the snapshot from what you entered so you have it in one place.</p>
<p>You shared <a href="{safe_url}">{safe_url}</a>, about <strong>${monthly_revenue_usd:,.0f}</strong> in monthly revenue, roughly <strong>{transactions_pm:,}</strong> orders per month, and about <strong>{cvr_percent:g}%</strong> CVR.</p>
<p>Framed the same way as on the calculator: with a <strong>monthly investment</strong> of about <strong>${fee:,.0f}</strong> on the <strong>{esc_plan}</strong> tier, the illustration implies about <strong>${lift:,.0f}</strong> in <strong>monthly revenue uplift</strong> (a planning figure from the model, not a promise). That works out to roughly <strong>{esc_roi} ROI</strong> against that monthly fee on those same assumptions.</p>
<p>Our <strong>guarantee</strong> on qualifying work for this tier is <strong>{esc_guar_body}</strong> as we publish it—happy to explain what that covers in plain language.</p>
<p>When we work with a store, the programme covers <strong>analytics, design, and development</strong> together so we can go from insight to shipped experiments without hand-offs stalling the work.</p>
<p>If you want a second pair of eyes on whether this kind of programme is a fit, the clearest next step is a free strategy session. No pitch deck—just your site, your goals, and a practical look at where we would start.</p>
<p><a href="{esc_schedule}">Schedule a free strategy session</a> — pick a time that works for you.</p>
<p>If you would rather browse first, here is our <a href="{esc_results}">results page with case studies</a>.</p>
<p>Reply to this email if something in the snapshot does not line up with how you think about the business—we are happy to sanity-check it.</p>
"""

    html_body = html_core + _closing_and_signature_html() + _signature_links_row_html(None) + "</body></html>"

    send_transactional_html(
        to_email=to_email,
        subject="Your CRO calculator snapshot",
        html_content=html_body,
        text_content=text_body,
        sender_name=sender_name,
        sender_email=sender,
        tags=["cro_cost_roi", "calculator_breakdown"],
    )


@main_bp.route("/cro-cost-roi/", methods=["GET"])
@main_bp.route("/cro-cost-roi", methods=["GET"])
def cro_cost_roi_landing():
    """Paid-ad landing: CRO cost vs ROI calculator (noindex)."""
    return render_template("landing_pages/cro_cost_roi_landing.html")


@main_bp.route("/cro-cost-roi/submit", methods=["POST"])
def cro_cost_roi_submit():
    """Persist calculator lead; recomputes model server-side from revenue."""
    data = request.get_json(silent=True) or request.form or {}
    fname = (data.get("fname") or "").strip()
    email = (data.get("email") or "").strip()
    website_raw = (data.get("website_url") or data.get("url") or "").strip()
    rev = _parse_usd_amount(data.get("monthly_revenue_usd"))
    ad_spend = _parse_usd_amount(data.get("monthly_ad_spend_usd"))
    txns = _parse_positive_int(data.get("transactions_per_month"))
    cvr = _parse_cvr_percent(data.get("cvr_percent"))
    aov = _parse_usd_amount(data.get("aov_usd"))

    if not fname:
        return jsonify({"success": False, "error": "Please enter your first name."}), 400
    if not email or not re.match(r"^[^\s@]+@[^\s@]+\.[^\s@]+$", email):
        return jsonify({"success": False, "error": "Please enter a valid work email."}), 400
    if _is_personal_email_domain(email):
        return jsonify(
            {
                "success": False,
                "error": "Please use your company or work email. We don't accept personal email addresses.",
            }
        ), 400
    if not website_raw:
        return jsonify({"success": False, "error": "Please enter your store URL."}), 400
    website_url = _normalize_shopify_url(website_raw) or website_raw
    if rev is None or rev < 50_000:
        return jsonify({"success": False, "error": "Invalid revenue. Run the calculator with at least $50k/month."}), 400
    if rev > 50_000_000:
        return jsonify({"success": False, "error": "Revenue out of range for this form—please email us instead."}), 400
    if txns is None or txns < 10:
        return jsonify({"success": False, "error": "Invalid calculator inputs (orders)."}), 400
    if cvr is None or cvr < 0.05 or cvr > 50:
        return jsonify({"success": False, "error": "Invalid calculator inputs (CVR)."}), 400
    if aov is not None and (aov < 1 or aov > 500_000):
        return jsonify({"success": False, "error": "Invalid calculator inputs (AOV)."}), 400

    snap = _compute_cro_cost_roi_snapshot(rev, txns)
    business_stage = _cro_cost_roi_business_stage_line(
        monthly_revenue_usd=rev,
        monthly_ad_spend_usd=ad_spend,
        snap=snap,
        transactions_pm=txns,
        cvr_percent=cvr,
        aov_usd=aov,
    )
    form_page_url = _ingest_form_page_url(data if isinstance(data, dict) else {})

    _save_lead(
        fname,
        email,
        "cro_cost_roi",
        resource_slug=None,
        business_stage=business_stage,
        website_url=website_url,
        form_page_url=form_page_url,
        orders_per_month=str(txns),
    )
    _sync_lead_to_brevo(
        fname,
        email,
        "cro_cost_roi",
        resource_slug=None,
        business_stage=business_stage,
        website_url=website_url,
    )
    _notify_slack_lead(
        fname,
        email,
        "cro_cost_roi",
        resource_slug=None,
        business_stage=business_stage,
        website_url=website_url,
    )
    if (current_app.config.get("BREVO_SENDER_EMAIL") or "").strip():
        try:
            _send_cro_cost_roi_results_email(
                to_email=email,
                fname=fname,
                monthly_revenue_usd=float(rev),
                transactions_pm=int(txns),
                cvr_percent=float(cvr),
                website_url=website_url,
                snap=snap,
            )
        except Exception as e:
            current_app.logger.exception("CRO cost ROI transactional email failed: %s", e)
            return jsonify(
                {
                    "success": False,
                    "error": "We saved your request but could not send the email. Please try again in a moment.",
                }
            ), 503
    return jsonify({"success": True})


@main_bp.route("/cro-scan/check", methods=["POST"])
def cro_scan_check():
    """Validate store URL: we must find both a product and a category page, or we decline (scan would be poor anyway)."""
    data = request.get_json(silent=True) or request.form or {}
    raw = (data.get("website_url") or data.get("url") or "").strip()
    _notify_slack_cro_scan_submit(raw)
    normalized = _normalize_shopify_url(raw)
    if not normalized:
        return jsonify({"success": False, "error": "Please enter a valid website URL."}), 400
    if not spark_backend.enabled():
        return jsonify({
            "success": False,
            "error": "CRO validation requires Spark (set SPARK_BACKEND_URL and SPARK_SITE_INGEST_SECRET).",
        }), 503
    chk = spark_backend.check_cro_store(website_url=normalized)
    if chk is None:
        return jsonify({
            "success": False,
            "error": "We couldn't validate this URL right now. Please try again.",
        }), 502
    if not chk.get("success"):
        return jsonify({"success": False, "error": chk.get("error") or "Invalid store URL."}), 400
    normalized = (chk.get("normalized_url") or normalized).strip()
    is_shopify = bool(chk.get("is_shopify", True))
    if is_shopify:
        _notify_slack_cro_scan_url(normalized)
    else:
        _notify_slack_cro_scan_non_shopify(normalized)
    from urllib.parse import quote

    thank_you_url = url_for("main.cro_scan_thank_you", url=quote(normalized, safe=""))
    return jsonify({"success": True, "redirect": thank_you_url})


def _sample_report_for_preview() -> dict:
    """Sample report dict for the HTML preview route (no PDF/email)."""
    return {
        "store_url": "https://example-store.com",
        "store_name": "Example Store",
        "overall_score": 72,
        "executive_summary": {
            "what_is_working": "Clear sale messaging and hero imagery. Product grid supports browsing. Add-to-cart is prominent on the product page.",
            "what_is_hurting": "Primary CTA is below the fold. Trust signals are buried in the footer. Product page could surface reviews and delivery info earlier.",
            "biggest_opportunity": "The biggest opportunity is product discovery and above-the-fold persuasion: shorten the path from homepage to product and surface trust earlier.",
        },
        "customer_research": {
            "target_audience_hypothesis": "Likely value-conscious shoppers; pricing and imagery suggest a mid-market, lifestyle-oriented audience.",
            "customer_motivations": "Quality, simplicity, and clear value. The site speaks to convenience and product appeal.",
            "customer_fears_frustrations": "Uncertainty about fit, returns, or delivery—not clearly addressed above the fold.",
            "desired_outcomes": "Easy choice, confidence in the purchase, smooth path from browsing to checkout.",
        },
        "pages": {
            "homepage": {
                "score": 68,
                "motivation": "Clear sale messaging and hero CTA invite action; trust badges support conversion.",
                "friction": ["Primary CTA is below the fold on mobile", "Trust signals (reviews, guarantees) not visible above fold"],
                "clarity": "Value proposition is present but could be stronger above the fold.",
                "anatomy": "Hero with banner; CTA appears after scroll. Consider moving primary CTA higher.",
                "page_anatomy": {"promise": "weak Could be stronger above the fold", "offer": "present Sale/CTA visible", "pain_point": "missing Not clearly stated", "solution": "present Hero and CTA", "social_proof": "weak In footer", "trust_signals": "weak In footer", "cta": "weak CTA below fold", "visual_hierarchy": "present Strong hero"},
                "page_summary": "The homepage's biggest weakness is that the primary CTA and trust elements are below the fold on mobile.",
                "ui_ux_notes": ["Clear visual hierarchy; hero and CTA stand out once in view.", "Body copy is scannable; consider shorter paragraphs for mobile.", "Primary button has good contrast; ensure tap target is at least 44px."],
                "testing_ideas": ["A/B test CTA copy (e.g. Shop Sale vs Get 20% Off)", "Test moving trust badges above fold", "Test hero with single CTA vs multiple links"],
                "screenshot_url": "https://image.thum.io/get/width/400/https://www.allbirds.com",
            },
            "collection": {
                "score": 74,
                "motivation": "Product grid and filters support browsing.",
                "friction": ["Filter options may overwhelm on mobile", "No sticky add-to-cart for quick actions"],
                "clarity": "Collection title and product count are clear.",
                "anatomy": "Standard grid; filters in drawer/sheet. Consider simplifying filter set on mobile.",
                "page_anatomy": {"promise": "present Browsing focus", "offer": "present Product grid", "pain_point": "missing", "solution": "present", "social_proof": "missing", "trust_signals": "missing", "cta": "weak", "visual_hierarchy": "present Clear grid"},
                "page_summary": "Collection page is functional but could reduce friction with a simpler filter set and quick-add option.",
                "ui_ux_notes": ["Product grid is consistent; card layout supports quick scanning.", "Filter controls may be small on mobile; consider larger tap targets."],
                "testing_ideas": ["A/B test number of products per row", "Test filter drawer vs inline filters", "Test Sort by default (e.g. Best selling vs New)"],
                "screenshot_url": "https://image.thum.io/get/width/400/https://www.allbirds.com/collections/all",
            },
            "product": {
                "score": 76,
                "above_the_fold": "Hero image, title and price are clear; add-to-cart is visible. Variant selector is present. Missing: reviews and delivery info in first viewport.",
                "below_the_fold": "Reviews and delivery/returns appear on scroll. Trust and secondary CTAs are present but could be surfaced higher.",
                "motivation": "Add to cart is prominent; images and price are clear.",
                "friction": ["Reviews section could be higher", "Delivery/returns info not immediately visible"],
                "clarity": "Product name and price are clear; benefit copy could be stronger.",
                "anatomy": "Gallery, title, price, ATC. Trust and delivery info further down.",
                "page_anatomy": {"promise": "present Product benefits", "offer": "present Price and ATC", "pain_point": "missing", "solution": "present", "social_proof": "weak Below fold", "trust_signals": "weak Below fold", "cta": "present Clear ATC", "visual_hierarchy": "present Strong gallery"},
                "page_summary": "The product page's biggest weakness is that reviews and delivery info are below the fold, which can increase doubt and bounce.",
                "ui_ux_notes": ["Gallery and price have strong hierarchy; ATC is easy to find.", "Variant selector is clear; ensure swatches are large enough on mobile.", "Reviews and delivery copy could use more spacing for readability."],
                "testing_ideas": ["A/B test ATC button copy (Add to bag vs Buy now)", "Test reviews placement (above vs below fold)", "Test sticky ATC bar on scroll"],
                "screenshot_url": "https://image.thum.io/get/width/400/https://www.allbirds.com/products/womens-wool-runners",
            },
        },
        "top_issues": [
            {
                "priority": 1, "page": "homepage", "title": "Primary CTA below fold on mobile",
                "description": "Move the main action button into the first viewport to reduce friction.",
                "impact": "High", "confidence": "High", "effort": "Low",
                "hypothesis": "If we move the primary CTA above the fold, add-to-cart and click-through will increase because fewer users will bounce before seeing the action.",
                "test_setup": "Variant A: control. Variant B: hero with primary CTA in first viewport.",
                "success_metric": "CTA click rate and add-to-cart rate from homepage.",
            },
            {
                "priority": 2, "page": "homepage", "title": "Trust signals missing above fold",
                "description": "Add reviews, guarantees or security badges near the hero to build confidence.",
                "impact": "Medium", "confidence": "Medium", "effort": "Low",
                "hypothesis": "If we surface trust badges above the fold, conversion will improve because doubt is reduced earlier.",
                "test_setup": "Variant A: control. Variant B: add 1–2 trust elements (e.g. star rating, guarantee) in hero.",
                "success_metric": "Add-to-cart rate and checkout rate.",
            },
            {
                "priority": 3, "page": "product", "title": "Reviews and delivery info lower on page",
                "description": "Surface key decision-making content higher to reduce scroll and doubt.",
                "impact": "High", "confidence": "High", "effort": "Medium",
                "hypothesis": "If we move reviews and delivery info into the first two viewports, we will see higher add-to-cart and lower bounce.",
                "test_setup": "Variant A: control. Variant B: reviews + delivery block above the fold or in expandable section.",
                "success_metric": "Add-to-cart rate and time to first interaction.",
            },
        ],
        "recommendations": [
            "Raise the primary CTA on the homepage so it’s visible without scrolling.",
            "Add 1–2 trust elements (e.g. star rating, guarantee) in the hero or just below.",
            "On product pages, move reviews and delivery/returns into the first two viewports.",
        ],
        "ugly_truth": "The biggest conversion leak is likely product discovery friction—too many steps between homepage and product, and key trust content is buried below the fold.",
        "fast_wins": [
            "Add trust badges (e.g. secure checkout, guarantee) near the hero or ATC.",
            "Improve product thumbnails (clear, consistent aspect ratio) on collection pages.",
            "Add shipping or returns info near the add-to-cart button.",
        ],
        "roadmap_90_days": {
            "month1": ["Navigation and homepage tests", "Above-the-fold CTA and trust tests"],
            "month2": ["PDP persuasion tests (reviews, delivery, sticky ATC)", "Collection quick-add and filters"],
            "month3": ["AOV and bundling tests", "Checkout simplification and urgency tests"],
        },
        "biggest_opportunity": {
            "title": "Product discovery",
            "explanation": "Too many steps between homepage and product; key trust content is buried. Featured products and clearer CTAs could shorten the path.",
            "why_it_matters": "Reducing friction and surfacing trust earlier typically lifts add-to-cart and checkout rates.",
            "example_tests": ["Featured products above the fold", "Quick add on collection", "Category shortcuts on homepage"],
        },
        "experiment_backlog": [
            "Sticky add-to-cart on PDP scroll", "Price anchoring", "Bundles on product page",
            "Social proof near CTA", "Quick add on collection", "Free-shipping threshold messaging",
            "Urgency near ATC", "Category shortcuts on homepage", "Featured products above the fold", "Simplified checkout",
        ],
        "next_steps": "Prioritize the fast wins, then run Month 1 roadmap tests. Use the experiment backlog to queue tests. Book a strategy call if you want help prioritizing and running experiments.",
        "what_good_looks_like": "A strong PDP has a sticky ATC, clear urgency (stock or delivery), and trust (reviews, guarantee) near the CTA. One high-converting pattern: hero image + title + price + ATC in the first viewport, with expandable reviews and delivery.",
    }


@main_bp.route("/cro-scan/report-preview/", methods=["GET"])
@main_bp.route("/cro-scan/report-preview", methods=["GET"])
def cro_scan_report_preview():
    """Preview the CRO report HTML template with sample data (for design/dev)."""
    from app.cro_report_normalize import _normalize_report

    report = _normalize_report(_sample_report_for_preview())
    return render_template("cro_scan_report.html", report=report)


@main_bp.route("/cro-scan/report/<token>", methods=["GET"])
def cro_scan_report_view(token):
    """Serve a stored CRO report by secret token. Only link holders can view; not listed or indexed."""
    t = (token or "").strip()
    if spark_backend.enabled():
        report = spark_backend.fetch_cro_scan_report_json(t)
        if not report:
            abort(404)
    else:
        rec = CroScanReport.query.filter_by(token=t).first()
        if not rec:
            abort(404)
        try:
            report = json.loads(rec.report_json)
        except (TypeError, ValueError):
            abort(404)
    from app.cro_report_normalize import _normalize_report

    report = _normalize_report(report if isinstance(report, dict) else {})
    resp = make_response(render_template("cro_scan_report.html", report=report))
    resp.headers["X-Robots-Tag"] = "noindex, nofollow"
    return resp


def _cro_scan_submissions_today() -> int:
    """Return a number 0–60 that increases over the day (UTC), slightly higher during business hours. Used for social proof."""
    from datetime import datetime
    now = datetime.utcnow()
    total_minutes = now.hour * 60 + now.minute
    fraction_of_day = total_minutes / (24 * 60)
    # Base: 0–50 by time of day; extra 0–10 during roughly 08:00–20:00 UTC so it feels more realistic
    base = int(fraction_of_day * 50)
    hour_frac = now.hour + now.minute / 60
    if 8 <= hour_frac < 20:
        bonus = int((hour_frac - 8) / 12 * 10)  # 0 at 08:00, up to 10 by 20:00
    else:
        bonus = 0
    count = base + bonus
    return min(max(count, 0), 60)


@main_bp.route("/cro-scan/thank-you/", methods=["GET"])
@main_bp.route("/cro-scan/thank-you", methods=["GET"])
def cro_scan_thank_you():
    """Thank you page: show store URL, desktop/mobile preview, email gate for report."""
    from urllib.parse import unquote
    url_param = request.args.get("url", "").strip()
    store_url = unquote(url_param) if url_param else None
    if not store_url:
        return redirect(url_for("main.cro_scan_landing"))
    normalized = _normalize_shopify_url(store_url)
    store_url = normalized or store_url
    submissions_today = _cro_scan_submissions_today()
    return render_template("cro_scan_thank_you.html", store_url=store_url, submissions_today=submissions_today)


@main_bp.route("/cro-scan/test-discovery/", methods=["GET", "POST"])
@main_bp.route("/cro-scan/test-discovery", methods=["GET", "POST"])
def cro_scan_test_discovery():
    """
    Test-only: discover home, collection, product for a domain. No report, no email, no scan.
    GET: form to enter URL. POST: run discovery and show result.
    """
    result = None
    if request.method == "POST":
        raw = (request.form.get("url") or request.form.get("website_url") or "").strip()
        normalized = _normalize_shopify_url(raw)
        if not normalized:
            result = {"error": "Invalid URL. Enter a domain (e.g. store.com or https://store.com)."}
        elif spark_backend.enabled():
            data = spark_backend.post_cro_test_discovery(url=raw, fast=False)
            if not data:
                result = {"error": "Discovery service unavailable (Spark).", "store_url": normalized}
            elif data.get("error"):
                result = {
                    "error": data.get("error"),
                    "store_url": data.get("store_url") or normalized,
                    "is_shopify": data.get("is_shopify"),
                }
            else:
                result = data
        else:
            result = {"error": "Set SPARK_BACKEND_URL for test discovery.", "store_url": normalized}
    return render_template("cro_scan_test_discovery.html", result=result)


@main_bp.route("/cro-scan/preview-image", methods=["GET"])
def cro_scan_preview_image():
    """
    Return screenshot for thank-you page preview (proxied from Spark when backend is enabled).
    """
    if not spark_backend.enabled():
        abort(503)
    params = {k: request.args.get(k, "") for k in ("url", "width") if request.args.get(k, "").strip()}
    if "url" not in params:
        abort(404)
    status, body = spark_backend.fetch_cro_preview_image(params=params)
    if status != 200 or not body:
        abort(404)
    resp = Response(body, mimetype="image/png")
    resp.headers["Cache-Control"] = "private, max-age=60"
    return resp


def _enqueue_cro_scan(
    store_url: str,
    email: str,
    fname: str,
    *,
    delivery_mode: str = "funnel",
    spark_attach_submission_type: str = "cro_scan",
) -> None:
    """Start the CRO scan pipeline on Spark (POST /api/site/cro-scan/run)."""
    if not spark_backend.enabled():
        current_app.logger.warning(
            "CRO scan skipped: set SPARK_BACKEND_URL and SPARK_SITE_INGEST_SECRET (store=%s email=%s)",
            (store_url or "")[:60],
            email,
        )
        return
    ok = spark_backend.trigger_cro_scan_run(
        store_url=store_url,
        email=email,
        fname=fname,
        delivery_mode=delivery_mode,
        spark_attach_submission_type=spark_attach_submission_type,
    )
    if not ok:
        current_app.logger.warning("CRO scan: Spark /cro-scan/run trigger failed for %s", (store_url or "")[:60])


def _maybe_enqueue_lead_magnet_background_scan(
    *,
    website_url: str | None,
    email: str,
    fname: str,
    submission_type: str,
) -> None:
    """
    Background CRO scan on Spark: ``POST /api/site/cro-scan/run`` with
    ``delivery_mode=lead_magnet_enrich`` (no report email; report stored + attached on Spark).

    Used after successful Spark ingest when the lead has a store URL (see ``_save_lead``).
    Requires SPARK_BACKEND_URL + secret + non-empty store URL.
    """
    if not spark_backend.enabled():
        return
    raw = (website_url or "").strip()
    if not raw:
        return
    store_url = _normalize_shopify_url(raw) or raw
    st = (submission_type or "audit").strip().lower()
    _enqueue_cro_scan(
        store_url,
        email,
        fname,
        delivery_mode="lead_magnet_enrich",
        spark_attach_submission_type=st,
    )


@main_bp.route("/cro-scan/submit-email", methods=["POST"])
def cro_scan_submit_email():
    """Save email + store URL + orders per month for CRO scan report; return success."""
    data = request.get_json(silent=True) or request.form or {}
    email = (data.get("email") or "").strip()
    store_url = (data.get("website_url") or data.get("url") or "").strip() or None
    orders_per_month = (data.get("orders_per_month") or "").strip() or None
    if not email or not re.match(r"^[^\s@]+@[^\s@]+\.[^\s@]+$", email):
        return jsonify({"success": False, "error": "Please enter a valid email address."}), 400
    if _is_personal_email_domain(email):
        return jsonify({
            "success": False,
            "error": "Please use your company or work email. We don't accept personal email addresses.",
        }), 400
    if not store_url:
        return jsonify({"success": False, "error": "Missing store URL."}), 400
    store_url = _normalize_shopify_url(store_url) or store_url
    fname = (email.split("@", 1)[0] or "").strip() or "Store owner"
    _save_lead(fname, email, "cro_scan", resource_slug=None, business_stage=orders_per_month, website_url=store_url)
    _sync_lead_to_brevo(fname, email, "cro_scan", resource_slug=None, business_stage=orders_per_month, website_url=store_url)
    _notify_slack_lead(fname, email, "cro_scan", resource_slug=None, business_stage=orders_per_month, website_url=store_url)
    nurture_lead_id = None
    form_page_url = _ingest_form_page_url(data if isinstance(data, dict) else {})
    if spark_backend.enabled():
        try:
            nurture_lead_id = spark_backend.register_nurture_cro_scan(
                email=email,
                store_url=store_url,
                fname=fname,
                orders_per_month=orders_per_month,
                form_page_url=form_page_url,
            )
        except Exception as e:
            current_app.logger.warning("spark_backend: nurture register failed: %s", e)
    elif current_app.config.get("CRO_NURTURE_ENABLED"):
        try:
            from app.cro_nurture.leads import create_nurture_lead_from_cro_scan_submit

            nurture_lead_id = create_nurture_lead_from_cro_scan_submit(
                email=email,
                store_url=store_url,
                fname=fname,
                orders_per_month=orders_per_month,
            )
        except Exception as e:
            current_app.logger.warning("cro_nurture: register lead failed: %s", e)
        if (
            nurture_lead_id
            and current_app.config.get("CRO_NURTURE_TEST_INSTANT_SEQUENCE")
            and current_app.debug
        ):
            import threading

            app = current_app._get_current_object()
            lid = nurture_lead_id

            def _instant_nurture():
                with app.app_context():
                    try:
                        from app.cro_nurture.services.test_pipeline import (
                            run_instant_test_sequence_after_submit,
                        )

                        out = run_instant_test_sequence_after_submit(lid)
                        app.logger.info("cro_nurture instant test lead=%s result=%s", lid, out)
                    except Exception:
                        app.logger.exception("cro_nurture instant test failed lead=%s", lid)

            threading.Thread(target=_instant_nurture, daemon=True).start()
    # Run scan pipeline in background (screenshots → AI → report email + Slack + attach)
    _enqueue_cro_scan(
        store_url,
        email,
        fname,
        delivery_mode="funnel",
        spark_attach_submission_type="cro_scan",
    )
    return jsonify({"success": True})
# Downloadable resources: slug -> filename in static/downloads/. Add new resources here.
RESOURCE_DOWNLOADS = {
    "13-bulletproof-strategies": {"filename": "sm-cro-ebook.pdf"},
}

@main_bp.route("/how-we-improve-conversions/")
@main_bp.route("/how-we-improve-conversions")
def how_we_improve_conversions():
    """VSL page: video + CTA button → short form (name, email, website) → Calendly. Goal: schedule a meeting."""
    return render_template("how-we-improve-conversions.html")


def _ingest_form_page_url(data: dict | None) -> str | None:
    """Resolve Spark `form_page_url` from JSON body or Referer. See docs/SPARK_SITE_LEAD_API.md."""
    d = data if isinstance(data, dict) else {}
    for k in ("form_page_url", "page_url", "submission_url"):
        v = (d.get(k) or "").strip()
        if v:
            return v
    ref = (request.referrer or "").strip()
    return ref or None


def _save_lead(
    fname: str,
    email: str,
    submission_type: str,
    resource_slug: str | None = None,
    business_stage: str | None = None,
    website_url: str | None = None,
    form_page_url: str | None = None,
    orders_per_month: str | None = None,
) -> None:
    """Persist lead to Postgres if DATABASE_URL is set. Logs errors, does not raise.

    When Spark is enabled, forwards to POST /api/site/lead — see docs/SPARK_SITE_LEAD_API.md.
    Nurture enrollment is controlled by SPARK_NURTURE_ENROLLMENT_TYPES (submission_type list).
    """
    if spark_backend.enabled():
        # CRO scan: submit-email posts once via register_nurture_cro_scan → Spark /api/site/lead
        # (avoids duplicate contact + nurture rows).
        if submission_type == "cro_scan":
            return
        try:
            from app.config import spark_background_cro_scan_after_ingest_enabled

            ok = spark_backend.post_form_lead(
                fname=fname,
                email=email,
                submission_type=submission_type,
                resource_slug=resource_slug,
                business_stage=business_stage,
                website_url=website_url,
                lead_origin="sparksmetrics.com",
                form_page_url=form_page_url,
                orders_per_month=orders_per_month,
            )
            if (
                ok
                and (website_url or "").strip()
                and spark_background_cro_scan_after_ingest_enabled()
            ):
                _maybe_enqueue_lead_magnet_background_scan(
                    website_url=website_url,
                    email=email,
                    fname=fname,
                    submission_type=submission_type,
                )
        except Exception as e:
            current_app.logger.warning("spark_backend site-lead failed: %s", e)
        return
    if not current_app.config.get("SQLALCHEMY_DATABASE_URI"):
        return
    try:
        lead = Lead(
            fname=fname,
            email=email,
            submission_type=submission_type,
            resource_slug=resource_slug,
            business_stage=(business_stage or "").strip() or None,
            website_url=(website_url or "").strip() or None,
        )
        db.session.add(lead)
        db.session.commit()
    except Exception as e:
        current_app.logger.warning("Failed to save lead: %s", e)
        db.session.rollback()


def _sync_lead_to_brevo(
    fname: str,
    email: str,
    submission_type: str,
    resource_slug: str | None = None,
    business_stage: str | None = None,
    website_url: str | None = None,
) -> None:
    """Add or update contact in Brevo if BREVO_API_KEY is set. Logs errors, does not raise."""
    if spark_backend.enabled():
        return
    api_key = (current_app.config.get("BREVO_API_KEY") or "").strip()
    if not api_key:
        current_app.logger.info("Brevo: BREVO_API_KEY not set in .env, skipping contact sync")
        return
    list_ids = list(current_app.config.get("BREVO_LIST_IDS") or [])
    if submission_type == "resource" and resource_slug == "13-bulletproof-strategies":
        cro_ebook_id = current_app.config.get("BREVO_CRO_EBOOK_LIST_ID")
        if cro_ebook_id and cro_ebook_id not in list_ids:
            list_ids.append(cro_ebook_id)
    if submission_type == "audit":
        audit_list_id = current_app.config.get("BREVO_AUDIT_LIST_ID")
        if audit_list_id and audit_list_id not in list_ids:
            list_ids.append(audit_list_id)
    if submission_type == "cro_scan":
        cro_scan_list_id = current_app.config.get("BREVO_CRO_SCAN_LIST_ID")
        if cro_scan_list_id and cro_scan_list_id not in list_ids:
            list_ids.append(cro_scan_list_id)
    if submission_type == "cro_cost_roi":
        audit_list_id = current_app.config.get("BREVO_AUDIT_LIST_ID")
        if audit_list_id and audit_list_id not in list_ids:
            list_ids.append(audit_list_id)
    attributes = {"FNAME": fname}
    if business_stage:
        attributes["BUSINESS_STAGE"] = business_stage
    if website_url:
        attributes["WEBSITE_URL"] = website_url
    payload = {
        "email": email,
        "attributes": attributes,
        "updateEnabled": True,
    }
    if list_ids:
        payload["listIds"] = list_ids
    try:
        import requests
    except ModuleNotFoundError:
        current_app.logger.warning(
            "Brevo sync skipped: install requests with: pip install requests"
        )
        return
    try:
        r = requests.post(
            BREVO_CONTACTS_URL,
            json=payload,
            headers={"api-key": api_key, "Content-Type": "application/json"},
            timeout=10,
        )
        if r.status_code in (200, 201, 204):
            current_app.logger.info("Brevo: contact synced for %s (lists: %s)", email, list_ids)
        else:
            current_app.logger.warning(
                "Brevo contact sync failed: HTTP %s – %s", r.status_code, (r.text or "")[:400]
            )
    except Exception as e:
        current_app.logger.warning("Brevo contact sync error: %s", e)


def _notify_slack_cro_scan_submit(raw_value: str) -> None:
    """Post to Slack every time someone submits the CRO scan form (button press + value). Logs errors, does not raise."""
    webhook_url = (current_app.config.get("SLACK_WEBHOOK_URL") or "").strip()
    if not webhook_url:
        return
    display = (raw_value or "(empty)").strip() or "(empty)"
    text = "CRO scan form submitted: {}".format(display)
    try:
        import requests
    except ModuleNotFoundError:
        current_app.logger.warning("Slack notify skipped: install requests (pip install requests)")
        return
    try:
        r = requests.post(
            webhook_url,
            json={"text": text},
            headers={"Content-Type": "application/json"},
            timeout=5,
        )
        if r.status_code != 200:
            current_app.logger.warning("Slack webhook failed: HTTP %s – %s", r.status_code, (r.text or "")[:200])
    except Exception as e:
        current_app.logger.warning("Slack notify error: %s", e)


def _notify_slack_cro_scan_non_shopify(store_url: str) -> None:
    """Post to Slack when someone submits a URL that is not detected as Shopify (scan still runs with generic discovery)."""
    webhook_url = (current_app.config.get("SLACK_WEBHOOK_URL") or "").strip()
    if not webhook_url:
        return
    text = "CRO scan: non-Shopify (generic ecommerce) URL submitted – scan will use category + product discovery: {}".format(store_url)
    try:
        import requests
    except ModuleNotFoundError:
        current_app.logger.warning("Slack notify skipped: install requests (pip install requests)")
        return
    try:
        r = requests.post(
            webhook_url,
            json={"text": text},
            headers={"Content-Type": "application/json"},
            timeout=5,
        )
        if r.status_code != 200:
            current_app.logger.warning("Slack webhook failed: HTTP %s – %s", r.status_code, (r.text or "")[:200])
    except Exception as e:
        current_app.logger.warning("Slack notify error: %s", e)


def _notify_slack_cro_scan_url(store_url: str) -> None:
    """Post to Slack when someone submits the CRO scan URL successfully. Logs errors, does not raise."""
    webhook_url = (current_app.config.get("SLACK_WEBHOOK_URL") or "").strip()
    if not webhook_url:
        return
    text = "CRO scan URL submitted: {}".format(store_url)
    try:
        import requests
    except ModuleNotFoundError:
        current_app.logger.warning("Slack notify skipped: install requests (pip install requests)")
        return
    try:
        r = requests.post(
            webhook_url,
            json={"text": text},
            headers={"Content-Type": "application/json"},
            timeout=5,
        )
        if r.status_code != 200:
            current_app.logger.warning("Slack webhook failed: HTTP %s – %s", r.status_code, (r.text or "")[:200])
    except Exception as e:
        current_app.logger.warning("Slack notify error: %s", e)


def _notify_slack_lead(
    fname: str,
    email: str,
    submission_type: str,
    resource_slug: str | None = None,
    business_stage: str | None = None,
    website_url: str | None = None,
) -> None:
    """Post a short message to Slack when a lead is submitted. Logs errors, does not raise."""
    webhook_url = (current_app.config.get("SLACK_WEBHOOK_URL") or "").strip()
    if not webhook_url:
        return
    if submission_type == "audit":
        label = "Free CRO audit"
    elif submission_type == "resource" and resource_slug == "13-bulletproof-strategies":
        label = "CRO ebook download"
    elif submission_type == "cro_scan":
        label = "CRO scan (Shopify)"
    elif submission_type == "cro_cost_roi":
        label = "CRO cost / ROI calculator"
    else:
        label = "Resource download"
    text = "New lead: *{}* <{}> – {}".format(fname, email, label)
    if business_stage:
        if submission_type == "cro_scan":
            text += "\nOrders per month: {}".format(business_stage)
        elif submission_type == "cro_cost_roi":
            text += "\nCalculator snapshot: {}".format(business_stage)
        else:
            text += "\nOrder volume / stage: {}".format(business_stage)
    if website_url:
        text += "\nWebsite: {}".format(website_url)
    try:
        import requests
    except ModuleNotFoundError:
        current_app.logger.warning("Slack notify skipped: install requests (pip install requests)")
        return
    try:
        r = requests.post(
            webhook_url,
            json={"text": text},
            headers={"Content-Type": "application/json"},
            timeout=5,
        )
        if r.status_code != 200:
            current_app.logger.warning("Slack webhook failed: HTTP %s – %s", r.status_code, (r.text or "")[:200])
    except Exception as e:
        current_app.logger.warning("Slack notify error: %s", e)


@main_bp.route("/client-event", methods=["POST"])
def client_event():
    """Receive lightweight client-side diagnostic events (beacon/POST)."""
    try:
        data = request.get_json(silent=True) or {}
        # Log to application logger
        current_app.logger.info("Client event received: %s", json.dumps(data or {}, ensure_ascii=False))
        # Persist to a JSONL file for later inspection (append only)
        try:
            from pathlib import Path

            log_dir = Path(__file__).resolve().parents[1] / "client_logs"
            log_dir.mkdir(parents=True, exist_ok=True)
            fp = log_dir / "client_events.jsonl"
            with fp.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps({"ts": datetime.now(timezone.utc).isoformat(), "data": data}, ensure_ascii=False) + "\n")
        except Exception as e:
            current_app.logger.warning("Failed to persist client event to file: %s", e)
    except Exception as e:
        current_app.logger.warning("Failed to record client event: %s", e)
    # always return 204 for beacons
    return ("", 204)


@main_bp.route("/webhook/calendly", methods=["POST"])
def calendly_webhook():
    """
    Receive Calendly webhooks (invitee.created, invitee.canceled, etc).
    Persist to file and optionally save invitee as a lead if email is present.
    """
    try:
        data = request.get_json(silent=True) or {}
    except Exception:
        data = {}
    try:
        current_app.logger.info("Calendly webhook received: %s", json.dumps(data or {}, ensure_ascii=False)[:2000])
    except Exception:
        pass
    # persist webhook payload
    try:
        from pathlib import Path

        log_dir = Path(__file__).resolve().parents[1] / "calendly_logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        fp = log_dir / "calendar_webhooks.jsonl"
        with fp.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"ts": datetime.now(timezone.utc).isoformat(), "payload": data}, ensure_ascii=False) + "\n")
    except Exception as e:
        current_app.logger.warning("Failed to persist calendly webhook: %s", e)

    # Attempt to save invitee as a lead if present (non-blocking)
    try:
        payload = data.get("payload") if isinstance(data, dict) else None
        invitee = None
        # Calendly webhook shapes vary; try common locations
        if isinstance(payload, dict):
            invitee = payload.get("invitee") or payload.get("questions_and_answers") or payload.get("event") and payload.get("event").get("invitee")
        if not invitee and isinstance(data, dict):
            # fallback older shapes
            invitee = data.get("invitee") or data.get("resource") or None
        email = None
        fname = None
        if isinstance(invitee, dict):
            email = (invitee.get("email") or invitee.get("email_address") or invitee.get("contact") or None)
            fname = invitee.get("name") or invitee.get("first_name") or None
        # If we have an email, save as a lead record (non-blocking)
        if email:
            try:
                # derive a short fname if absent
                use_fname = (fname or "").strip() or (email.split("@", 1)[0] if "@" in email else "")
                _save_lead(use_fname, email, "calendly", resource_slug=None)
            except Exception as e:
                current_app.logger.warning("Failed to save calendly lead: %s", e)
    except Exception:
        pass

    # Respond to Calendly quickly
    return jsonify({"status": "ok"})


@main_bp.route("/_admin/client-events")
def admin_client_events():
    """Return recent client events (only accessible from localhost)."""
    # Allow access only from localhost for safety
    try:
        remote = request.remote_addr or ""
        if remote not in ("127.0.0.1", "::1", "localhost"):
            abort(404)
        from pathlib import Path

        log_dir = Path(__file__).resolve().parents[1] / "client_logs"
        fp = log_dir / "client_events.jsonl"
        if not fp.exists():
            return jsonify({"events": []})
        lines = fp.read_text(encoding="utf-8", errors="ignore").strip().splitlines()
        # return last 100 events
        last = lines[-100:]
        events = []
        for l in last:
            try:
                events.append(json.loads(l))
            except Exception:
                events.append({"raw": l})
        return jsonify({"events": events})
    except Exception:
        abort(500)


@main_bp.route("/request-audit", methods=["POST"])
def request_audit():
    """Collect fname, email, and optional website_url for free CRO audit request; returns success (no file)."""
    data = request.get_json(silent=True) or {}
    fname = (data.get("fname") or "").strip()
    email = (data.get("email") or "").strip()
    website_url = (data.get("website_url") or "").strip() or None
    if not fname:
        return jsonify({"success": False, "error": "First name required"}), 400
    if not email or not re.match(r"^[^\s@]+@[^\s@]+\.[^\s@]+$", email):
        return jsonify({"success": False, "error": "Invalid email"}), 400
    if website_url:
        website_url = _normalize_shopify_url(website_url) or website_url
    _save_lead(
        fname,
        email,
        "audit",
        resource_slug=None,
        website_url=website_url,
        form_page_url=_ingest_form_page_url(data),
    )
    _sync_lead_to_brevo(fname, email, "audit", resource_slug=None, website_url=website_url)
    _notify_slack_lead(fname, email, "audit", resource_slug=None, website_url=website_url)
    _maybe_enqueue_lead_magnet_background_scan(
        website_url=website_url,
        email=email,
        fname=fname,
        submission_type="audit",
    )
    return jsonify({"success": True})


@main_bp.route("/download-resource", methods=["POST"])
def download_resource():
    """Collect fname and email for resource download; return download URL. Resource slug in body."""
    data = request.get_json(silent=True) or {}
    fname = (data.get("fname") or "").strip()
    email = (data.get("email") or "").strip()
    slug = (data.get("resource") or "").strip()
    business_stage = (data.get("business_stage") or "").strip() or None
    website_url_lm = (data.get("website_url") or data.get("store_url") or "").strip() or None
    if not fname:
        return jsonify({"success": False, "error": "First name required"}), 400
    if not email or not re.match(r"^[^\s@]+@[^\s@]+\.[^\s@]+$", email):
        return jsonify({"success": False, "error": "Invalid email"}), 400
    resource = RESOURCE_DOWNLOADS.get(slug) if slug else None
    if not resource:
        return jsonify({"success": False, "error": "Unknown resource"}), 400
    if website_url_lm:
        website_url_lm = _normalize_shopify_url(website_url_lm) or website_url_lm
    _save_lead(
        fname,
        email,
        "resource",
        resource_slug=slug or None,
        business_stage=business_stage,
        website_url=website_url_lm,
        form_page_url=_ingest_form_page_url(data),
    )
    _sync_lead_to_brevo(
        fname,
        email,
        "resource",
        resource_slug=slug or None,
        business_stage=business_stage,
        website_url=website_url_lm,
    )
    _notify_slack_lead(
        fname,
        email,
        "resource",
        resource_slug=slug or None,
        business_stage=business_stage,
        website_url=website_url_lm,
    )
    download_url = url_for("main.serve_download", slug=slug)
    return jsonify({"success": True, "download_url": download_url})


@main_bp.route("/download/<slug>")
def serve_download(slug: str):
    """Serve a resource file as attachment. No HTML page—direct download. Not indexed (X-Robots-Tag)."""
    resource = RESOURCE_DOWNLOADS.get(slug.strip()) if slug else None
    if not resource:
        abort(404)
    filename = resource["filename"]
    downloads_dir = Path(current_app.static_folder) / "downloads"
    path = downloads_dir / filename
    if not path.is_file():
        abort(404)
    resp = send_file(
        path,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=filename,
    )
    resp.headers["X-Robots-Tag"] = "noindex, nofollow"
    return resp


@main_bp.route("/analytics")
def analytics():
    """Marketing analytics & tracking service landing."""
    return render_template("analytics.html")


@main_bp.route("/results")
def results():
    """Results & case studies — combined page."""
    return render_template("results.html")


@main_bp.route("/results/<slug>")
def case_study(slug):
    """Individual portfolio / case study page."""
    case = CASE_STUDIES.get(slug)
    if not case:
        abort(404)
    return render_template("case_study.html", case=case)


def _parse_blog_date(s: str):
    """Parse published_date 'DD Mon YYYY' for sorting. Returns datetime or datetime.min on failure."""
    if not s:
        return datetime.min
    try:
        return datetime.strptime(s.strip(), "%d %b %Y")
    except (ValueError, TypeError):
        return datetime.min


@main_bp.route("/blog")
def blog_index():
    """Blog overview page."""
    # Prefer scanning templates/blog/ so the index reflects templates present in templates/blog/.
    posts = _scan_blog_templates() or _load_blog_posts()
    posts = sorted(posts, key=lambda p: _parse_blog_date(p.get("published_date") or ""), reverse=True)
    return render_template("blog.html", posts=posts)


@main_bp.route("/blog/<slug>")
def blog_post(slug: str):
    """Individual blog post page (template per post)."""
    posts = _scan_blog_templates() or _load_blog_posts()
    post = next((p for p in posts if p.get("slug") == slug), None)
    if not post:
        abort(404)
    return render_template(post["template"], post=post)


@main_bp.route("/privacy-policy")
def privacy_policy():
    """Privacy policy."""
    return render_template("privacy_policy.html")


@main_bp.route("/terms")
def terms():
    """Terms and conditions."""
    return render_template("terms.html")


@main_bp.route("/terms-and-conditions")
def terms_and_conditions():
    """Terms and conditions (alternate URL)."""
    return render_template("terms.html")


@main_bp.route("/sitemap.xml")
def sitemap():
    """Generate sitemap XML with all public pages and case study URLs. Excludes /thank-you/ (noindex, post-lead redirect)."""
    pages = [
        ("main.index", {}),
        ("main.cro", {}),
        ("main.analytics", {}),
        ("main.results", {}),
        ("main.blog_index", {}),
        ("main.schedule_a_call", {}),
        ("main.cro_ebook", {}),
        ("main.privacy_policy", {}),
        ("main.terms", {}),
    ]
    urls = []
    for endpoint, kwargs in pages:
        try:
            urls.append(url_for(endpoint, _external=True, **kwargs))
        except Exception:
            pass
    for slug in CASE_STUDIES:
        try:
            urls.append(url_for("main.case_study", slug=slug, _external=True))
        except Exception:
            pass
    for post in _load_blog_posts():
        try:
            urls.append(url_for("main.blog_post", slug=post["slug"], _external=True))
        except Exception:
            pass
    def escape_loc(s: str) -> str:
        return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;").replace("'", "&apos;")

    xml_lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ]
    for loc in urls:
        xml_lines.append("  <url>")
        xml_lines.append(f"    <loc>{escape_loc(loc)}</loc>")
        xml_lines.append("  </url>")
    xml_lines.append("</urlset>")
    return Response("\n".join(xml_lines), mimetype="application/xml")


@main_bp.route("/robots.txt")
def robots():
    """Serve robots.txt allowing crawlers and pointing to sitemap."""
    base = request.url_root.rstrip("/")
    body = f"""User-agent: *
Allow: /
Disallow: /download/
Disallow: /cro-scan/

Sitemap: {base}/sitemap.xml
"""
    return Response(body, mimetype="text/plain")
