"""Main (public) routes."""
import re
from flask import abort, Blueprint, current_app, jsonify, redirect, render_template, request, url_for, Response

from app.models import Lead, db

BREVO_CONTACTS_URL = "https://api.brevo.com/v3/contacts"

main_bp = Blueprint("main", __name__)

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


@main_bp.route("/")
def index():
    """Home page — CRO landing (light theme)."""
    return render_template("landing_alt.html")


@main_bp.route("/favicon.ico")
def favicon():
    """Redirect to SVG favicon so browsers that request .ico get the icon."""
    return redirect(url_for("static", filename="favicon.svg"))


@main_bp.route("/cro")
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


# Downloadable resources: slug -> filename in static/downloads/. Add new resources here.
RESOURCE_DOWNLOADS = {
    "cro-checklist": {"filename": "13-bulletproof-strategies-conversions-sparksmetrics.pdf"},
}


def _save_lead(fname: str, email: str, submission_type: str, resource_slug: str | None = None) -> None:
    """Persist lead to Postgres if DATABASE_URL is set. Logs errors, does not raise."""
    if not current_app.config.get("SQLALCHEMY_DATABASE_URI"):
        return
    try:
        lead = Lead(
            fname=fname,
            email=email,
            submission_type=submission_type,
            resource_slug=resource_slug,
        )
        db.session.add(lead)
        db.session.commit()
    except Exception as e:
        current_app.logger.warning("Failed to save lead: %s", e)
        db.session.rollback()


def _sync_lead_to_brevo(
    fname: str, email: str, submission_type: str, resource_slug: str | None = None
) -> None:
    """Add or update contact in Brevo if BREVO_API_KEY is set. Logs errors, does not raise."""
    api_key = (current_app.config.get("BREVO_API_KEY") or "").strip()
    if not api_key:
        current_app.logger.info("Brevo: BREVO_API_KEY not set in .env, skipping contact sync")
        return
    list_ids = list(current_app.config.get("BREVO_LIST_IDS") or [])
    if submission_type == "resource" and resource_slug == "cro-checklist":
        cro_ebook_id = current_app.config.get("BREVO_CRO_EBOOK_LIST_ID")
        if cro_ebook_id and cro_ebook_id not in list_ids:
            list_ids.append(cro_ebook_id)
    if submission_type == "audit":
        audit_list_id = current_app.config.get("BREVO_AUDIT_LIST_ID")
        if audit_list_id and audit_list_id not in list_ids:
            list_ids.append(audit_list_id)
    payload = {
        "email": email,
        "attributes": {"FNAME": fname},
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


def _notify_slack_lead(
    fname: str, email: str, submission_type: str, resource_slug: str | None = None
) -> None:
    """Post a short message to Slack when a lead is submitted. Logs errors, does not raise."""
    webhook_url = (current_app.config.get("SLACK_WEBHOOK_URL") or "").strip()
    if not webhook_url:
        return
    if submission_type == "audit":
        label = "Free CRO audit"
    elif submission_type == "resource" and resource_slug == "cro-checklist":
        label = "CRO ebook download"
    else:
        label = "Resource download"
    text = "New lead: *{}* <{}> – {}".format(fname, email, label)
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


@main_bp.route("/request-audit", methods=["POST"])
def request_audit():
    """Collect fname and email for free CRO audit request; returns success (no file)."""
    data = request.get_json(silent=True) or {}
    fname = (data.get("fname") or "").strip()
    email = (data.get("email") or "").strip()
    if not fname:
        return jsonify({"success": False, "error": "First name required"}), 400
    if not email or not re.match(r"^[^\s@]+@[^\s@]+\.[^\s@]+$", email):
        return jsonify({"success": False, "error": "Invalid email"}), 400
    _save_lead(fname, email, "audit", resource_slug=None)
    _sync_lead_to_brevo(fname, email, "audit", resource_slug=None)
    return jsonify({"success": True})


@main_bp.route("/download-resource", methods=["POST"])
def download_resource():
    """Collect fname and email for resource download; return download URL. Resource slug in body."""
    data = request.get_json(silent=True) or {}
    fname = (data.get("fname") or "").strip()
    email = (data.get("email") or "").strip()
    slug = (data.get("resource") or "").strip()
    if not fname:
        return jsonify({"success": False, "error": "First name required"}), 400
    if not email or not re.match(r"^[^\s@]+@[^\s@]+\.[^\s@]+$", email):
        return jsonify({"success": False, "error": "Invalid email"}), 400
    resource = RESOURCE_DOWNLOADS.get(slug) if slug else None
    if not resource:
        return jsonify({"success": False, "error": "Unknown resource"}), 400
    _save_lead(fname, email, "resource", resource_slug=slug or None)
    _sync_lead_to_brevo(fname, email, "resource", resource_slug=slug or None)
    _notify_slack_lead(fname, email, "resource", resource_slug=slug or None)
    download_url = url_for("static", filename="downloads/" + resource["filename"])
    return jsonify({"success": True, "download_url": download_url})


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


@main_bp.route("/case-studies")
def case_studies():
    """Case studies — redirect to Results."""
    return redirect(url_for("main.results"), code=301)


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


@main_bp.route("/earnings-disclaimer")
def earnings_disclaimer():
    """Earnings disclaimer — placeholder until page is built."""
    return render_template("placeholder.html", title="Earnings Disclaimer")


@main_bp.route("/sitemap.xml")
def sitemap():
    """Generate sitemap XML with all public pages and case study URLs."""
    pages = [
        ("main.index", {}),
        ("main.cro", {}),
        ("main.analytics", {}),
        ("main.results", {}),
        ("main.schedule_a_call", {}),
        ("main.cro_ebook", {}),
        ("main.privacy_policy", {}),
        ("main.terms", {}),
        ("main.earnings_disclaimer", {}),
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

Sitemap: {base}/sitemap.xml
"""
    return Response(body, mimetype="text/plain")
