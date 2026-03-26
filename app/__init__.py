"""Sparksmetrics Flask application factory."""
import importlib
import os
from datetime import datetime
from pathlib import Path

import click
from dotenv import load_dotenv
from flask import Flask, render_template, request

from app.models import db
from app.routes.main import CASE_STUDIES, CASE_STUDY_ORDER, main_bp
from app.youtube import get_latest_video_ids

# Load .env from project root (parent of app/) so it works regardless of cwd
_env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_env_path)


def _sparksmetrics_uses_spark_backend() -> bool:
    """When True, marketing DB + nurture live on Spark; this app only runs UI + scan worker."""
    return bool(
        (os.getenv("SPARK_BACKEND_URL") or "").strip() and (os.getenv("SPARK_SITE_INGEST_SECRET") or "").strip()
    )


def _read_env_var(path: Path, key: str) -> str:
    """Read a single KEY from .env file; return value or empty string."""
    if not path.exists():
        return ""
    try:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip().replace("\r", "")
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            if k.strip() == key:
                return v.strip().strip("'\"").replace("\r", "") or ""
    except Exception:
        pass
    return ""


def create_app(config_object="app.config.Config") -> Flask:
    """Create and configure the Flask application."""
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.config.from_object(config_object)

    # Ensure BREVO/Slack/OpenAI/Browserless from .env (avoids import-order issues with config module)
    if not (app.config.get("BREVO_API_KEY") or "").strip():
        app.config["BREVO_API_KEY"] = _read_env_var(_env_path, "BREVO_API_KEY")
    if not (app.config.get("SLACK_WEBHOOK_URL") or "").strip():
        app.config["SLACK_WEBHOOK_URL"] = _read_env_var(_env_path, "SLACK_WEBHOOK_URL")
    _openai = (app.config.get("OPENAI_API_KEY") or "").strip() or (app.config.get("OPEN_AI_KEY") or "").strip()
    if not _openai:
        _openai = _read_env_var(_env_path, "OPEN_AI_KEY") or _read_env_var(_env_path, "OPENAI_API_KEY")
    if _openai:
        app.config["OPENAI_API_KEY"] = _openai
        app.config["OPEN_AI_KEY"] = _openai
    if not (app.config.get("BROWSERLESS_API_TOKEN") or "").strip():
        app.config["BROWSERLESS_API_TOKEN"] = _read_env_var(_env_path, "BROWSERLESS_API_TOKEN")

    # Ensure DATABASE_URL is set when running from script/certain environments (config may load from elsewhere)
    if not app.config.get("SQLALCHEMY_DATABASE_URI") and _env_path.exists():
        try:
            for line in _env_path.read_text(encoding="utf-8", errors="replace").splitlines():
                if "DATABASE_URL=" in line:
                    v = line.split("=", 1)[1].strip().strip("'\"").replace("\r", "")
                    if v:
                        app.config["SQLALCHEMY_DATABASE_URI"] = v.replace("postgres://", "postgresql://", 1)
                    break
        except Exception:
            pass

    # Fallback: local SQLite so the app runs without DATABASE_URL (e.g. local dev)
    if not (app.config.get("SQLALCHEMY_DATABASE_URI") or "").strip():
        _base = Path(__file__).resolve().parent.parent
        app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{(_base / 'local.db').as_posix()}"

    db.init_app(app)
    with app.app_context():
        if app.config.get("SQLALCHEMY_DATABASE_URI"):
            if not _sparksmetrics_uses_spark_backend():
                from app.models import Lead, CroScanReport  # noqa: F401
                if app.config.get("CRO_NURTURE_ENABLED"):
                    importlib.import_module("app.cro_nurture.models")
            db.create_all()
            if app.config.get("CRO_NURTURE_ENABLED") and not _sparksmetrics_uses_spark_backend():
                from app.cro_nurture.sequence_schedule import ensure_default_sequence_from_schedule

                ensure_default_sequence_from_schedule()

    app.register_blueprint(main_bp)

    if app.config.get("CRO_NURTURE_ENABLED") and not _sparksmetrics_uses_spark_backend():
        from app.cro_nurture.routes import cro_nurture_bp

        app.register_blueprint(cro_nurture_bp)

    @app.errorhandler(404)
    def page_not_found(e):
        return render_template("404.html"), 404

    @app.after_request
    def static_cache_and_embed(response):
        """Static files: cacheable and safe to load from elsewhere (e.g. email signature images)."""
        if request.path.startswith("/static/"):
            response.headers.set("Cache-Control", "public, max-age=31536000, immutable")  # 1 year, immutable for speed
            # Don’t restrict who can load the resource (email clients, external referrers)
            if "Content-Security-Policy" not in response.headers:
                response.headers.set("X-Content-Type-Options", "nosniff")
        return response

    @app.context_processor
    def inject_now():
        return {"now": datetime.utcnow}

    @app.context_processor
    def inject_primary_bar():
        """Primary bar: month name + slots (3 on days 1–10, 2 on 11–20, 1 on 21–31)."""
        utc = datetime.utcnow()
        day = utc.day
        if day <= 10:
            slots = 3
        elif day <= 20:
            slots = 2
        else:
            slots = 1
        return {
            "primary_bar_month": utc.strftime("%B"),
            "primary_bar_slots": slots,
        }

    # Default video IDs when nothing is configured (so gallery always shows something)
    _DEFAULT_YT_IDS = ["vbUI7BW8PNI", "BKN3rEt45Sk", "qEd0zrqFYeg"]

    @app.context_processor
    def inject_youtube_videos():
        """Inject YouTube video IDs for gallery: config list, else channel RSS, else default IDs."""
        manual_ids = app.config.get("YOUTUBE_VIDEO_IDS") or []
        if manual_ids:
            video_ids = list(manual_ids)[:12]
        else:
            channel_id = app.config.get("YOUTUBE_CHANNEL_ID") or ""
            video_ids = get_latest_video_ids(channel_id, max_results=8) if channel_id else []
        if not video_ids:
            video_ids = _DEFAULT_YT_IDS
        return {"youtube_video_ids": video_ids}

    @app.context_processor
    def inject_case_studies():
        """Inject ordered case studies for cards (homepage + results). Single source of truth."""
        case_studies_list = [
            (slug, CASE_STUDIES[slug]) for slug in CASE_STUDY_ORDER if slug in CASE_STUDIES
        ]
        return {"case_studies_list": case_studies_list}

    @app.cli.command("db-upgrade")
    def db_upgrade():
        """Add any missing columns to existing tables (e.g. after model changes). Safe to run multiple times."""
        with app.app_context():
            from app.models import db
            from sqlalchemy import text
            conn = db.engine.connect()
            try:
                # SQLite: add columns to leads if missing (create_all doesn't alter existing tables)
                if "sqlite" in str(db.engine.url):
                    for col, spec in [("business_stage", "VARCHAR(120)"), ("website_url", "VARCHAR(500)")]:
                        try:
                            conn.execute(text(f"ALTER TABLE leads ADD COLUMN {col} {spec}"))
                            conn.commit()
                            print(f"  Added column leads.{col}")
                        except Exception as e:
                            conn.rollback()
                            if "duplicate column" in str(e).lower():
                                pass  # already exists
                            else:
                                raise
                else:
                    # PostgreSQL: failed ALTER aborts the transaction — must rollback before next statement
                    for col, spec in [("business_stage", "VARCHAR(120)"), ("website_url", "VARCHAR(500)")]:
                        try:
                            conn.execute(text(f"ALTER TABLE leads ADD COLUMN {col} {spec}"))
                            conn.commit()
                            print(f"  Added column leads.{col}")
                        except Exception as e:
                            conn.rollback()
                            if "already exists" in str(e).lower() or "duplicate" in str(e).lower():
                                pass
                            else:
                                raise
            finally:
                conn.close()
            print("Done. Run db.create_all() if you need new tables (e.g. cro_scan_reports).")

    @app.cli.command("cro-nurture-sync-sequence")
    @click.option("--force", is_flag=True, help="Replace existing step rows from sequence_schedule.py")
    def cro_nurture_sync_sequence(force):
        """Apply app/cro_nurture/sequence_schedule.py (STEPS) to the database."""
        with app.app_context():
            if _sparksmetrics_uses_spark_backend():
                print("SPARK_BACKEND_URL is set — run cro-nurture-sync-sequence on the Spark app.")
                return
            if not app.config.get("CRO_NURTURE_ENABLED"):
                print("Enable CRO_NURTURE_ENABLED=1 first (creates cro_nurture_* tables on startup).")
                return
            from app.cro_nurture.sequence_schedule import apply_scheduled_steps_to_database

            print(apply_scheduled_steps_to_database(replace_existing=force))

    @app.cli.command("cro-nurture-lead-show")
    @click.argument("lead_id", type=int, required=False)
    def cro_nurture_lead_show(lead_id):
        """Print scan + enrichment summary for one cro_nurture_lead (default: latest row by id)."""
        import json as json_lib

        with app.app_context():
            if _sparksmetrics_uses_spark_backend():
                print("SPARK_BACKEND_URL is set — inspect leads on Spark (see docs/SPARKS_SITE_BACKEND.md).")
                return
            if not app.config.get("CRO_NURTURE_ENABLED"):
                print("Enable CRO_NURTURE_ENABLED=1 first.")
                return
            from app.cro_nurture.models import CroNurtureLead
            from app.cro_nurture.services.enrichment import dump_lead_enrichment_summary

            lid = lead_id
            if lid is None:
                last = CroNurtureLead.query.order_by(CroNurtureLead.id.desc()).first()
                if not last:
                    print("No cro_nurture_lead rows.")
                    return
                lid = last.id
                print(f"# using latest lead id={lid}\n")
            data = dump_lead_enrichment_summary(lid)
            print(json_lib.dumps(data, indent=2, ensure_ascii=False, default=str))

    @app.cli.command("cro-nurture-lead-enrich")
    @click.argument("lead_id", type=int)
    def cro_nurture_lead_enrich(lead_id):
        """Re-run homepage fetch + OpenAI business_profile for a lead (no CRO form submit)."""
        import json as json_lib

        with app.app_context():
            if _sparksmetrics_uses_spark_backend():
                print("SPARK_BACKEND_URL is set — run this command on Spark.")
                return
            if not app.config.get("CRO_NURTURE_ENABLED"):
                print("Enable CRO_NURTURE_ENABLED=1 first.")
                return
            from app.cro_nurture.services.enrichment import force_re_enrich_lead

            out = force_re_enrich_lead(lead_id)
            print(json_lib.dumps(out, indent=2, ensure_ascii=False, default=str))

    @app.cli.command("cro-nurture-lead-due-now")
    @click.argument("lead_id", type=int, required=False)
    def cro_nurture_lead_due_now(lead_id):
        """Set a lead's next_send_at to now so the next nurture step is eligible to send."""
        import json as json_lib
        from datetime import datetime

        with app.app_context():
            if _sparksmetrics_uses_spark_backend():
                print("SPARK_BACKEND_URL is set — run this command on Spark.")
                return
            if not app.config.get("CRO_NURTURE_ENABLED"):
                print("Enable CRO_NURTURE_ENABLED=1 first.")
                return
            from app.cro_nurture.models import CroNurtureLead

            lid = lead_id
            if lid is None:
                last = CroNurtureLead.query.order_by(CroNurtureLead.id.desc()).first()
                if not last:
                    print("No cro_nurture_lead rows.")
                    return
                lid = last.id
                print(f"# using latest lead id={lid}\n")
            lead = CroNurtureLead.query.get(lid)
            if not lead:
                print(json_lib.dumps({"error": "not_found", "lead_id": lid}))
                return
            if lead.unsubscribed_at:
                print(json_lib.dumps({"error": "unsubscribed", "lead_id": lid}))
                return
            if lead.paused:
                print(json_lib.dumps({"error": "paused", "lead_id": lid}))
                return
            if lead.enrichment_status not in ("ok", "failed"):
                print(
                    json_lib.dumps(
                        {"error": "enrichment_not_ready", "lead_id": lid, "status": lead.enrichment_status}
                    )
                )
                return
            lead.next_send_at = datetime.utcnow()
            db.session.commit()
            print(
                json_lib.dumps(
                    {
                        "ok": True,
                        "lead_id": lid,
                        "next_step_order": lead.next_step_order,
                        "next_send_at": lead.next_send_at.isoformat() if lead.next_send_at else None,
                        "hint": "Run: flask --app run cro-nurture-dispatch",
                    },
                    indent=2,
                    default=str,
                )
            )

    @app.cli.command("cro-nurture-dispatch")
    def cro_nurture_dispatch():
        """Send due nurture emails (OpenAI + Brevo). Uses multi-round dispatch when TEST_ZERO_DELAYS is on."""
        import json as json_lib

        with app.app_context():
            if _sparksmetrics_uses_spark_backend():
                print("SPARK_BACKEND_URL is set — run this command on Spark.")
                return
            if not app.config.get("CRO_NURTURE_ENABLED"):
                print("Enable CRO_NURTURE_ENABLED=1 first.")
                return
            from app.cro_nurture.services.dispatch import run_dispatch_batch_until_quiet

            out = run_dispatch_batch_until_quiet()
            print(json_lib.dumps(out, indent=2))

    @app.cli.command("cro-nurture-lead-burst")
    @click.argument("lead_id", type=int)
    @click.option("--max-steps", default=15, show_default=True, help="Safety cap on emails in one run")
    def cro_nurture_lead_burst(lead_id, max_steps):
        """Send all remaining nurture steps for one lead in one command (dev; forces each step due)."""
        import json as json_lib

        with app.app_context():
            if _sparksmetrics_uses_spark_backend():
                print("SPARK_BACKEND_URL is set — run this command on Spark.")
                return
            if not app.config.get("CRO_NURTURE_ENABLED"):
                print("Enable CRO_NURTURE_ENABLED=1 first.")
                return
            from app.cro_nurture.services.dispatch import run_cli_burst_nurture_lead

            out = run_cli_burst_nurture_lead(lead_id, max_steps=max_steps)
            print(json_lib.dumps(out, indent=2, default=str))

    @app.cli.command("cro-nurture-lead-reset-sequence")
    @click.argument("lead_id", type=int)
    def cro_nurture_lead_reset_sequence(lead_id):
        """Dev: clear send history and rewind lead to step 1 (re-run burst to test all emails again)."""
        import json as json_lib

        with app.app_context():
            if _sparksmetrics_uses_spark_backend():
                print("SPARK_BACKEND_URL is set — run this command on Spark.")
                return
            if not app.config.get("CRO_NURTURE_ENABLED"):
                print("Enable CRO_NURTURE_ENABLED=1 first.")
                return
            from app.cro_nurture.services.dispatch import reset_nurture_lead_sequence_for_retest

            out = reset_nurture_lead_sequence_for_retest(lead_id)
            print(json_lib.dumps(out, indent=2, default=str))

    @app.cli.command("cro-nurture-cron")
    def cro_nurture_cron():
        """Run enrichment batch, then dispatch (same work as POST /cro-nurture/api/cron/run)."""
        import json as json_lib

        with app.app_context():
            if _sparksmetrics_uses_spark_backend():
                print("SPARK_BACKEND_URL is set — run this command on Spark.")
                return
            if not app.config.get("CRO_NURTURE_ENABLED"):
                print("Enable CRO_NURTURE_ENABLED=1 first.")
                return
            from app.cro_nurture.services.dispatch import run_dispatch_batch_until_quiet
            from app.cro_nurture.services.enrichment import run_enrichment_batch

            en = run_enrichment_batch()
            di = run_dispatch_batch_until_quiet()
            print(json_lib.dumps({"enrichment": en, "dispatch": di}, indent=2))

    @app.cli.command("cro-scan-test")
    @click.option("--url", default="https://outdoorresearch.com", help="Store URL to scan")
    @click.option("--out", default="cro_scan_report_test.pdf", help="Output PDF path")
    def cro_scan_test(url, out):
        """Run a one-off CRO scan and save the report PDF (no email). For testing."""
        import sys
        store_url = url.strip() if url else "https://outdoorresearch.com"
        if not store_url.startswith("http"):
            store_url = "https://" + store_url
        with app.app_context():
            from app.cro_scan.screenshots import get_screenshot_urls
            from app.cro_scan.ai_analysis import analyze_screenshots
            from app.cro_scan.report import build_report_pdf
            print("1. Getting mobile screenshot URLs...", flush=True)
            try:
                screenshot_urls = get_screenshot_urls(store_url)
            except Exception as e:
                print(f"   Error: {e}", file=sys.stderr)
                sys.exit(1)
            for k, v in screenshot_urls.items():
                print(f"   {k}: {v[:70]}..." if v and len(v) > 70 else f"   {k}: {v or '(none)'}")
            print("2. Running AI analysis (OpenAI vision)...", flush=True)
            report = analyze_screenshots(store_url, screenshot_urls)
            print(f"   Overall score: {report.get('overall_score')}, store: {report.get('store_name')}")
            from app.cro_scan.ai_analysis import _empty_page_dict
            for page_key in ("homepage", "collection", "product"):
                if not isinstance(report.get("pages", {}).get(page_key), dict):
                    report.setdefault("pages", {})[page_key] = _empty_page_dict()
                url_val = screenshot_urls.get(page_key) or ""
                if url_val:
                    report["pages"][page_key]["screenshot_url"] = url_val
            print("3. Building report...", flush=True)
            from flask import render_template
            html = render_template("cro_scan_report.html", report=report)
            out_dir = Path(__file__).resolve().parent.parent
            html_path = out_dir / (Path(out).stem + ".html")
            html_path.write_text(html, encoding="utf-8")
            print(f"   HTML saved: {html_path}")
            try:
                pdf_bytes = build_report_pdf(report)
                if pdf_bytes:
                    out_path = out_dir / out
                    out_path.write_bytes(pdf_bytes)
                    print(f"   PDF saved: {out_path}")
                else:
                    print("   PDF skipped (empty). Open the HTML file in a browser to view the report.")
            except Exception as e:
                print(f"   PDF skipped ({e}). Open the HTML file in a browser to view the report.")

    return app
