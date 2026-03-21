"""Send CRO report ready email via Brevo (link to on-site report only; no PDF attachment)."""
from __future__ import annotations

from flask import current_app


BREVO_SMTP_EMAIL_URL = "https://api.brevo.com/v3/smtp/email"

EMAIL_SIGNATURE_HTML = """
<p>If there's anything I can help with, let me know.</p>
<div><br></div>
<div>Thanks,</div>
<div><br>
<table cellpadding="0" cellspacing="0" border="0" style="font-family: Arial, Helvetica, sans-serif; font-size: 13px; line-height: 1.5; color: #1a1a1b;">
  <tbody><tr>
    <td>
      <table cellpadding="0" cellspacing="0" border="0">
        <tbody><tr>
          <td style="padding: 0 0 8px 0;">
            <a href="https://sparksmetrics.com/" style="text-decoration: none;"><img src="https://sparksmetrics.com/static/images/signature-logo-name.png" width="195" height="40" alt="Sparksmetrics" style="display: block; width: 195px; height: 40px; border: 0;"></a>
          </td>
        </tr>
        <tr>
          <td style="padding: 0 0 2px 0; font-size: 13px; color: #1a1a1b;"><strong>Stijn Wollerich</strong></td>
        </tr>
        <tr>
          <td style="padding: 0 0 8px 0; font-size: 12px; color: #6b7280;"> </td>
        </tr>
        <tr>
          <td style="padding: 0 0 6px 0;">
            <span style="font-size: 12px;">sparksmetrics.com</span>
          </td>
        </tr>
        <tr>
          <td style="padding: 0;">
            <a href="https://sparksmetrics.com/how-we-improve-conversions" style="color: #ff4d00; font-weight: 700; text-decoration: none; font-size: 12px;">Book a call</a>
          </td>
        </tr>
      </tbody></table>
    </td>
  </tr>
</tbody></table>
</div>
"""


def send_report_email(
    to_email: str,
    fname: str,
    store_name: str,
    *,
    report_view_url: str | None = None,
) -> bool:
    """
    Send the CRO report email via Brevo transactional API.
    Uses report_view_url only (no PDF attachment).
    Returns True if sent successfully, False otherwise (logs errors).
    """
    api_key = (current_app.config.get("BREVO_API_KEY") or "").strip()
    if not api_key:
        current_app.logger.warning("CRO scan: BREVO_API_KEY not set, cannot send report email")
        return False

    sender_email = (current_app.config.get("BREVO_SENDER_EMAIL") or "").strip()
    sender_name = (current_app.config.get("BREVO_SENDER_NAME") or "Sparksmetrics").strip()
    if not sender_email:
        current_app.logger.warning("CRO scan: BREVO_SENDER_EMAIL not set, cannot send report email")
        return False

    subject = f"Your CRO Scan Report: {store_name}"
    greeting_name = (fname or "").strip() or "there"
    report_cta_url = "https://sparksmetrics.com/how-we-improve-conversions"
    if report_view_url:
        html_body = f"""
    <p>Hi {greeting_name},</p>
    <p>Your CRO scan report for <strong>{store_name}</strong> is ready.</p>
    <p><a href="{report_view_url}" style="display:inline-block;padding:12px 24px;background:#FF4D00;color:#ffffff !important;font-weight:bold;text-decoration:none;border-radius:8px;">View your report online</a></p>
    <p>Take your time exploring the report. When you’re ready to turn these insights into real growth, discover our risk-free CRO program—guaranteed results, or your money back. <a href="{report_cta_url}">See how we improve conversions</a>.</p>
    <p>Questions? Reply to this email or <a href="{report_cta_url}">learn more here</a>.</p>
    {EMAIL_SIGNATURE_HTML}
    """
    else:
        html_body = f"""
    <p>Hi {greeting_name},</p>
    <p>Your CRO scan for <strong>{store_name}</strong> is ready, but we couldn&rsquo;t create a secure view link just now. Reply to this email and we&rsquo;ll send you access.</p>
    <p>If you&rsquo;d like to turn these insights into results, we offer a guaranteed CRO program&mdash;or your money back. <a href="{report_cta_url}">See how we improve conversions</a>.</p>
    <p>Questions? Reply to this email or <a href="{report_cta_url}">learn more here</a>.</p>
    {EMAIL_SIGNATURE_HTML}
    """

    payload = {
        "sender": {"email": sender_email, "name": sender_name},
        "to": [{"email": to_email}],
        "subject": subject,
        "htmlContent": html_body,
    }

    try:
        import requests
        r = requests.post(
            BREVO_SMTP_EMAIL_URL,
            json=payload,
            headers={"api-key": api_key, "Content-Type": "application/json"},
            timeout=15,
        )
        if r.status_code in (200, 201, 202, 204):
            current_app.logger.info("CRO scan: report email sent to %s", to_email)
            return True
        current_app.logger.warning(
            "CRO scan: Brevo send failed HTTP %s – %s",
            r.status_code,
            (r.text or "")[:300],
        )
        return False
    except Exception as e:
        current_app.logger.warning("CRO scan: send report email error: %s", e)
        return False
