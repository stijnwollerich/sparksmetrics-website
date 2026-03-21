"""Brevo REST: sync contact + send transactional HTML."""

from __future__ import annotations

import os

import requests


def _api_key() -> str:
    try:
        from flask import has_request_context, current_app

        if has_request_context():
            k = (current_app.config.get("BREVO_API_KEY") or "").strip()
            if k:
                return k
    except Exception:
        pass
    return (os.getenv("BREVO_API_KEY") or "").strip()


def _headers():
    key = _api_key()
    if not key:
        raise RuntimeError("BREVO_API_KEY is not set")
    return {
        "accept": "application/json",
        "content-type": "application/json",
        "api-key": key,
    }


def upsert_contact(
    *,
    email: str,
    first_name: str | None,
    last_name: str | None,
    list_ids: list[int],
    attributes: dict | None = None,
) -> bool:
    url = "https://api.brevo.com/v3/contacts"
    attrs = {"FIRSTNAME": first_name or "", "LASTNAME": last_name or ""}
    if attributes:
        attrs.update(attributes)
    data = {
        "email": email,
        "updateEnabled": True,
        "attributes": attrs,
    }
    if list_ids:
        data["listIds"] = list_ids
    r = requests.post(url, headers=_headers(), json=data, timeout=30)
    return r.status_code in (200, 201, 204)


def send_transactional_html(
    *,
    to_email: str,
    subject: str,
    html_content: str,
    text_content: str | None,
    sender_name: str,
    sender_email: str,
    reply_to: str | None = None,
    tags: list[str] | None = None,
) -> dict:
    url = "https://api.brevo.com/v3/smtp/email"
    payload = {
        "sender": {"name": sender_name, "email": sender_email},
        "to": [{"email": to_email}],
        "subject": subject,
        "htmlContent": html_content,
    }
    if text_content:
        payload["textContent"] = text_content
    if reply_to:
        payload["replyTo"] = {"email": reply_to}
    if tags:
        payload["tags"] = tags[:10]
    r = requests.post(url, headers=_headers(), json=payload, timeout=60)
    data: dict = {}
    try:
        data = r.json()
    except Exception:
        data = {"raw": r.text}
    if r.status_code >= 400:
        raise RuntimeError(f"Brevo send failed {r.status_code}: {data}")
    return data
