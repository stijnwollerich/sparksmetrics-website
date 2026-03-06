"""Discover Shopify pages and build mobile screenshot URLs (thum.io or Scrapfly)."""
from __future__ import annotations

import re
from urllib.parse import quote, urljoin, urlparse


# Mobile viewport width for thum.io (larger = better detail in report; display is ~340px)
MOBILE_WIDTH = 600
# Viewport height in px (crop). Works on free tier; fullpage/ needs paid. Docs don't state a max for crop; 3k captures a good chunk of page.
CRO_SCREENSHOT_HEIGHT = 3000


def mobile_screenshot_url(page_url: str, width: int = MOBILE_WIDTH, height: int = CRO_SCREENSHOT_HEIGHT) -> str:
    """Return thum.io URL for a mobile screenshot (width x height viewport; no fullpage so free tier works)."""
    return f"https://image.thum.io/get/width/{width}/crop/{height}/{page_url}"


def discover_pages(store_url: str) -> dict[str, str]:
    """
    Discover homepage, one collection page, and one product page for a Shopify store.
    Returns dict: {"homepage": url, "collection": url or "", "product": url or ""}.
    """
    from flask import current_app
    import requests

    base = store_url.rstrip("/")
    out: dict[str, str] = {
        "homepage": base,
        "collection": "",
        "product": "",
    }

    try:
        r = requests.get(
            base,
            timeout=10,
            headers={"User-Agent": "Mozilla/5.0 (compatible; Sparksmetrics-CRO-Scan/1.0)"},
            allow_redirects=True,
        )
        if r.status_code != 200:
            return out
        html = (r.text or "")[:150000]
    except Exception as e:
        current_app.logger.warning("CRO scan: failed to fetch store for discovery: %s", e)
        return out

    # Find first /collections/... link (prefer /collections/all or a real collection)
    coll_match = re.search(r'href=["\']([^"\']*(?:/collections/[a-zA-Z0-9_-]+)["\']?)', html, re.I)
    if coll_match:
        href = coll_match.group(1).split('"')[0].split("'")[0].strip()
        out["collection"] = urljoin(base + "/", href)
    if not out["collection"]:
        out["collection"] = urljoin(base + "/", "/collections/all")

    # Find first /products/... link on homepage (href or data-href)
    prod_match = re.search(
        r'(?:href|data-href)=["\']([^"\']*?/products/[a-zA-Z0-9_.%-]+)["\']?',
        html, re.I
    )
    if prod_match:
        href = prod_match.group(1).split('"')[0].split("'")[0].strip()
        out["product"] = urljoin(base + "/", href)

    # Fallback: any /products/... path in the page (e.g. in JSON or URLs)
    if not out["product"]:
        fallback = re.search(r'(https?://[^"\'\s<>]*?/products/[a-zA-Z0-9_.%-]+|/products/[a-zA-Z0-9_.%-]+)', html, re.I)
        if fallback:
            raw = fallback.group(1).strip()
            out["product"] = raw if raw.startswith("http") else urljoin(base + "/", raw)

    # If still no product, try collection page for a product link
    if not out["product"] and out["collection"]:
        try:
            r2 = requests.get(
                out["collection"],
                timeout=8,
                headers={"User-Agent": "Mozilla/5.0 (compatible; Sparksmetrics-CRO-Scan/1.0)"},
                allow_redirects=True,
            )
            if r2.status_code == 200:
                html2 = (r2.text or "")[:150000]
                prod_match2 = re.search(
                    r'(?:href|data-href)=["\']([^"\']*?/products/[a-zA-Z0-9_.%-]+)["\']?',
                    html2, re.I
                )
                if prod_match2:
                    href2 = prod_match2.group(1).split('"')[0].split("'")[0].strip()
                    out["product"] = urljoin(base + "/", href2)
                if not out["product"]:
                    fallback2 = re.search(r'(https?://[^"\'\s<>]*?/products/[a-zA-Z0-9_.%-]+|/products/[a-zA-Z0-9_.%-]+)', html2, re.I)
                    if fallback2:
                        raw2 = fallback2.group(1).strip()
                        out["product"] = raw2 if raw2.startswith("http") else urljoin(base + "/", raw2)
        except Exception:
            pass

    # Shopify fallback: /products.json returns first N products (no HTML parsing)
    if not out["product"]:
        try:
            products_url = urljoin(base + "/", "/products.json?limit=1")
            r3 = requests.get(
                products_url,
                timeout=8,
                headers={"User-Agent": "Mozilla/5.0 (compatible; Sparksmetrics-CRO-Scan/1.0)"},
            )
            if r3.status_code == 200:
                data = r3.json()
                products = data.get("products") or []
                if products:
                    handle = products[0].get("handle")
                    if handle:
                        out["product"] = urljoin(base + "/", f"/products/{handle}")
        except Exception:
            pass

    # If still no product, try first collection's products.json (e.g. /collections/all/products.json)
    if not out["product"] and out["collection"]:
        try:
            # e.g. https://store.com/collections/all -> https://store.com/collections/all/products.json
            coll_path = urlparse(out["collection"]).path.strip("/")
            if coll_path:
                coll_json = urljoin(base + "/", f"{coll_path}/products.json?limit=1")
                r4 = requests.get(
                    coll_json,
                    timeout=8,
                    headers={"User-Agent": "Mozilla/5.0 (compatible; Sparksmetrics-CRO-Scan/1.0)"},
                )
                if r4.status_code == 200:
                    data = r4.json()
                    products = data.get("products") or []
                    if products:
                        handle = products[0].get("handle")
                        if handle:
                            out["product"] = urljoin(base + "/", f"/products/{handle}")
        except Exception:
            pass

    return out


def scrapfly_screenshot_api_url(page_url: str, api_key: str) -> str:
    """
    Return Scrapfly screenshot API URL for the given page (Cloudflare bypass).
    Caller must pass api_key; do not log the returned URL (contains key).
    """
    base = "https://api.scrapfly.io/screenshot"
    # Mobile viewport, full page, PNG. Timeout 60s. Doc: capture=fullpage, resolution=375x812
    encoded_url = quote(page_url, safe="")
    return f"{base}?url={encoded_url}&key={quote(api_key, safe='')}&format=png&capture=fullpage&resolution=375x812&timeout=60000"


def get_screenshot_urls(store_url: str) -> dict[str, str]:
    """
    Return dict of page_name -> URL for homepage, collection, product.
    When BROWSERLESS_API_TOKEN or SCRAPFLY_API_KEY is set: returns raw page URLs (fetched via that provider in ai_analysis).
    Otherwise: returns thum.io screenshot URLs. Keys: homepage, collection, product.
    """
    from flask import current_app

    pages = discover_pages(store_url)
    if current_app.config.get("BROWSERLESS_API_TOKEN") or current_app.config.get("SCRAPFLY_API_KEY"):
        return {
            "homepage": pages["homepage"],
            "collection": pages.get("collection") or "",
            "product": pages.get("product") or "",
        }
    return {
        "homepage": mobile_screenshot_url(pages["homepage"]),
        "collection": mobile_screenshot_url(pages["collection"]) if pages.get("collection") else "",
        "product": mobile_screenshot_url(pages["product"]) if pages.get("product") else "",
    }
