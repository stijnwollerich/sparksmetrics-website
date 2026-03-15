"""Detect ecommerce platform (Shopify vs generic) for CRO scan. Wappalyzer-style detection from HTML."""
from __future__ import annotations

import re


# Signatures that indicate an ecommerce platform (from HTML/headers). Order matters: first match wins for some.
# Each tuple: (platform_id, list of patterns). Pattern can be str (substring in html) or compiled regex.
_ECOMMERCE_SIGNATURES: list[tuple[str, list]] = [
    ("shopify", [
        "cdn.shopify.com",
        "shopify.com/shopify.js",
        "Shopify.theme",
        "shopify-section",
        re.compile(r"shopify\.com/store/"),
    ]),
    ("woocommerce", [
        "wp-content/plugins/woocommerce",
        "woocommerce-no-js",
        "wc-add-to-cart",
        "wc-block-",
        "wc_cart_fragments",
        "woocommerce-page",
        "product type-",
        "product_cat",
        "add_to_cart",
        "data-product_id",
        "single_add_to_cart_button",
        "class=\"woocommerce",
        "class='woocommerce",
        "?add-to-cart=",
        "add-to-cart",
        re.compile(r"woocommerce[/\-]"),
        re.compile(r"href=[\"']/product/"),  # WooCommerce product URL pattern
    ]),
    ("magento", [
        "Magento",
        "skin/frontend/",
        "MAGE_",
        "var/requirejs",
        "mage/",
    ]),
    ("bigcommerce", [
        "bigcommerce.com",
        "stencil",
        "cdn11.bigcommerce.com",
        "data-bc-",
    ]),
    ("wix", [
        "wix.com",
        "wixstatic.com",
        "wix-warmup-data",
    ]),
    ("squarespace", [
        "squarespace.com",
        "squarespace-cdn.com",
        "sqsp",
    ]),
    ("prestashop", [
        "prestashop",
        "prestashop.js",
    ]),
    ("opencart", [
        "opencart",
        "catalog/view/theme",
    ]),
]


def detect_ecommerce_platform(html: str, *, max_chars: int = 150000) -> str | None:
    """
    Detect which ecommerce platform the site uses (Wappalyzer-style).
    html: page source (typically homepage).
    Returns platform id (e.g. 'shopify', 'woocommerce', 'magento', 'bigcommerce') or None.
    """
    if not html:
        return None
    haystack = (html[:max_chars] if len(html) > max_chars else html).lower()
    for platform_id, patterns in _ECOMMERCE_SIGNATURES:
        for p in patterns:
            if isinstance(p, re.Pattern):
                if p.search(haystack):
                    return platform_id
            else:
                if p.lower() in haystack:
                    return platform_id
    # Fallback: WordPress site with /product/ URLs is almost certainly WooCommerce
    if "wp-content" in haystack and "/product/" in haystack:
        return "woocommerce"
    return None


def is_shopify_store(url: str) -> bool:
    """Return True if the URL is a Shopify store (myshopify.com or response contains Shopify)."""
    if not url:
        return False
    from urllib.parse import urlparse
    try:
        p = urlparse(url)
        host = (p.netloc or "").lower()
        if host.endswith(".myshopify.com") or host == "myshopify.com":
            return True
    except Exception:
        pass
    try:
        import requests
        r = requests.get(
            url,
            timeout=8,
            headers={"User-Agent": "Mozilla/5.0 (compatible; Sparksmetrics-CRO-Scan/1.0)"},
            allow_redirects=True,
        )
        if r.status_code != 200:
            return False
        text = (r.headers.get("X-Shopify-Stage") or "") + (r.text[:20000] if r.text else "")
        return "shopify" in text.lower() or "cdn.shopify.com" in (r.text or "")[:20000]
    except Exception:
        return False
