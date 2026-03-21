"""Normalize POST body for /api/ingest (JSON, form, multipart)."""

from __future__ import annotations

import json
from typing import Any

from flask import Request


def extract_ingest_secret(request: Request) -> str:
    got = request.headers.get("X-Cro-Nurture-Secret") or request.headers.get("X-CRO-NURTURE-SECRET")
    auth = request.headers.get("Authorization") or ""
    if auth.lower().startswith("bearer "):
        got = got or auth[7:].strip()
    if got:
        return str(got).strip()
    payload = request.get_json(silent=True)
    if isinstance(payload, dict):
        v = payload.get("ingest_secret")
        if v is not None and str(v).strip():
            return str(v).strip()
    v = request.form.get("ingest_secret")
    if v is not None and str(v).strip():
        return str(v).strip()
    return ""


def merge_ingest_payload(request: Request) -> dict[str, Any]:
    data: dict[str, Any] = {}
    j = request.get_json(silent=True)
    if isinstance(j, dict):
        data.update(j)
    for key, v in request.form.items():
        if key == "ingest_secret":
            continue
        if key not in data or data.get(key) in (None, ""):
            data[key] = v
    data.pop("ingest_secret", None)
    return data


def pick_site_url(data: dict[str, Any]) -> str:
    for k in ("site_url", "website", "url", "scan_url", "site", "domain"):
        v = data.get(k)
        if v is not None and str(v).strip():
            return str(v).strip()
    return ""


def pick_email(data: dict[str, Any]) -> str:
    v = data.get("email") or data.get("Email") or data.get("email_address")
    return str(v).strip().lower() if v else ""


def pick_names(data: dict[str, Any]) -> tuple[str | None, str | None]:
    fn = (data.get("first_name") or data.get("firstName") or "").strip() or None
    ln = (data.get("last_name") or data.get("lastName") or "").strip() or None
    if fn or ln:
        return fn, ln
    full = (data.get("name") or data.get("full_name") or data.get("Name") or "").strip()
    if not full:
        return None, None
    parts = full.split(None, 1)
    return parts[0] or None, (parts[1] if len(parts) > 1 else None)


def pick_cro_scan_raw(data: dict[str, Any]):
    for k in ("cro_scan", "cro_scan_payload", "scan", "scan_results", "results", "cro_results"):
        if k in data and data[k] not in (None, ""):
            return data[k]
    return None


def parse_cro_payload(cro_raw):
    if cro_raw is None:
        return None
    if isinstance(cro_raw, str):
        try:
            return json.loads(cro_raw)
        except json.JSONDecodeError:
            return {"raw": cro_raw[:50_000]}
    if isinstance(cro_raw, dict):
        return cro_raw
    return {"value": str(cro_raw)[:50_000]}
