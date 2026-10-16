"""PDP redesign offer — vertical copy, Stripe Checkout helpers, UTM helpers."""
from __future__ import annotations

import os
from typing import Any
from urllib.parse import urlencode

# Server-rendered so ?v= never flashes default copy.
PDP_VERTICALS: dict[str, dict[str, str]] = {
    "default": {
        "eyebrow": "For Shopify & ecomm brands doing $100K+/month",
        "headline": "We'll redesign your product page to convert more of the traffic you're already paying for.",
    },
    "puzzle": {
        "eyebrow": "For puzzle & games brands doing $100K+/mo",
        "headline": "We'll redesign your product page to convert more of the traffic you're already paying for.",
    },
    "beauty": {
        "eyebrow": "For beauty & skincare brands doing $100K+/mo",
        "headline": "We'll redesign your product page to convert more of the traffic you're already paying for.",
    },
    "supplements": {
        "eyebrow": "For supplement & wellness brands doing $100K+/mo",
        "headline": "We'll redesign your product page to convert more of the traffic you're already paying for.",
    },
    "apparel": {
        "eyebrow": "For apparel & fashion brands doing $100K+/mo",
        "headline": "We'll redesign your product page to convert more of the traffic you're already paying for.",
    },
    "home": {
        "eyebrow": "For home & lifestyle brands doing $100K+/mo",
        "headline": "We'll redesign your product page to convert more of the traffic you're already paying for.",
    },
}

PDP_PRICE_USD = 500
PDP_PRICE_CENTS = PDP_PRICE_USD * 100
PDP_OFFER_NAME = "PDP Redesign"

UTM_KEYS = ("utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "utm_id")


def resolve_vertical(v: str | None) -> dict[str, str]:
    key = (v or "").strip().lower()
    if key and key in PDP_VERTICALS and key != "default":
        return {"key": key, **PDP_VERTICALS[key]}
    return {"key": "default", **PDP_VERTICALS["default"]}


def collect_utm_params(args: Any) -> dict[str, str]:
    out: dict[str, str] = {}
    for k in UTM_KEYS:
        val = (args.get(k) or "").strip()
        if val:
            out[k] = val[:200]
    return out


def stripe_configured() -> bool:
    return bool((os.environ.get("STRIPE_SECRET_KEY") or "").strip())


def get_calendly_url() -> str:
    return (
        os.environ.get("PDP_REDESIGN_CALENDLY_URL")
        or "https://calendly.com/stijn-wollerich/conversion-rate-optimization?hide_gdpr_banner=1"
    ).strip()


def get_meta_pixel_id() -> str:
    return (os.environ.get("META_PIXEL_ID") or "").strip()


def create_checkout_session(
    *,
    success_url: str,
    cancel_url: str,
    metadata: dict[str, str],
    customer_email: str | None = None,
) -> str:
    """Create a Stripe Checkout Session and return the hosted URL."""
    import stripe

    secret = (os.environ.get("STRIPE_SECRET_KEY") or "").strip()
    if not secret:
        raise RuntimeError("STRIPE_SECRET_KEY is not set")

    stripe.api_key = secret
    price_id = (os.environ.get("STRIPE_PDP_PRICE_ID") or "").strip()

    params: dict[str, Any] = {
        "mode": "payment",
        "success_url": success_url,
        "cancel_url": cancel_url,
        "metadata": metadata,
        "payment_intent_data": {"metadata": metadata},
        "allow_promotion_codes": False,
        "billing_address_collection": "auto",
    }
    if customer_email:
        params["customer_email"] = customer_email

    if price_id:
        params["line_items"] = [{"price": price_id, "quantity": 1}]
    else:
        params["line_items"] = [
            {
                "quantity": 1,
                "price_data": {
                    "currency": "usd",
                    "unit_amount": PDP_PRICE_CENTS,
                    "product_data": {
                        "name": PDP_OFFER_NAME,
                        "description": "Full product page redesign in Figma + video walkthrough. Delivered in 5 business days.",
                    },
                },
            }
        ]

    session = stripe.checkout.Session.create(**params)
    if not session.url:
        raise RuntimeError("Stripe did not return a checkout URL")
    return session.url


def retrieve_checkout_session(session_id: str) -> dict[str, Any] | None:
    """Fetch Checkout Session details (email, payment status, metadata)."""
    import stripe

    secret = (os.environ.get("STRIPE_SECRET_KEY") or "").strip()
    if not secret or not session_id:
        return None
    stripe.api_key = secret
    try:
        session = stripe.checkout.Session.retrieve(session_id)
    except Exception:
        return None
    email = (
        (getattr(session, "customer_details", None) and session.customer_details.email)
        or getattr(session, "customer_email", None)
        or ""
    )
    name = ""
    details = getattr(session, "customer_details", None)
    if details and getattr(details, "name", None):
        name = details.name or ""
    return {
        "id": session.id,
        "email": (email or "").strip(),
        "name": (name or "").strip(),
        "payment_status": getattr(session, "payment_status", None),
        "amount_total": getattr(session, "amount_total", None),
        "metadata": dict(getattr(session, "metadata", None) or {}),
    }


def append_query(url: str, params: dict[str, str]) -> str:
    if not params:
        return url
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}{urlencode(params)}"
