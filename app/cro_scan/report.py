"""Build HTML report from JSON and convert to PDF (weasyprint)."""
from __future__ import annotations

import io
from flask import current_app, render_template


def render_report_html(report: dict) -> str:
    """Render the CRO report HTML template with the given report dict."""
    return render_template("cro_scan_report.html", report=report)


def html_to_pdf(html: str) -> bytes:
    """Convert HTML string to PDF bytes using weasyprint."""
    try:
        from weasyprint import HTML
        from weasyprint.text.fonts import FontConfiguration
    except ImportError:
        current_app.logger.warning("CRO scan: weasyprint not installed, cannot generate PDF")
        return b""

    font_config = FontConfiguration()
    pdf_buffer = io.BytesIO()
    HTML(string=html).write_pdf(pdf_buffer, font_config=font_config)
    return pdf_buffer.getvalue()


def build_report_pdf(report: dict) -> bytes:
    """Render report to HTML and convert to PDF. Returns PDF bytes."""
    html = render_report_html(report)
    return html_to_pdf(html)
