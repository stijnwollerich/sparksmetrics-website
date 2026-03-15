"""Discover Shopify pages and build mobile screenshot URLs (thum.io or Scrapfly)."""
from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import quote, urljoin, urlparse


# Mobile viewport width for thum.io (larger = better detail in report; display is ~340px)
MOBILE_WIDTH = 600
# Viewport height in px (crop). Works on free tier; fullpage/ needs paid. Docs don't state a max for crop; 3k captures a good chunk of page.
CRO_SCREENSHOT_HEIGHT = 3000


def mobile_screenshot_url(page_url: str, width: int = MOBILE_WIDTH, height: int = CRO_SCREENSHOT_HEIGHT) -> str:
    """Return thum.io URL for a mobile screenshot (width x height viewport; no fullpage so free tier works)."""
    return f"https://image.thum.io/get/width/{width}/crop/{height}/{page_url}"


def discover_pages(store_url: str, *, fast: bool = False) -> dict[str, str]:
    """
    Discover homepage, one collection page, and one product page for a Shopify store.
    fast=True: use shorter timeouts (3–4s) for quick validation only.
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
    t = 3 if fast else 10
    t_secondary = 3 if fast else 8

    try:
        r = requests.get(
            base,
            timeout=t,
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
                timeout=t_secondary,
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
                timeout=t_secondary,
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
                    timeout=t_secondary,
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


# Patterns for generic ecommerce: category (collection) and product URLs in href.
# Include non-English WooCommerce bases (categorie, winkel, kategorie, categoria, etc.).
_CATEGORY_PATTERNS = [
    r'href=["\']([^"\']*?/(?:product-category|product-categorie)/(?:[a-zA-Z0-9_.%-]+/)*[a-zA-Z0-9_.%-]*)["\']?',
    r'href=["\']([^"\']*?/(?:categor(?:y|ies|ie|ien|ia|ias)|kategor(?:y|ie|ien))/(?:[a-zA-Z0-9_.%-]+/)*[a-zA-Z0-9_.%-]*)["\']?',
    r'href=["\']([^"\']*?/(?:produkt-kategorie|categoria-producto)/(?:[a-zA-Z0-9_.%-]+/)*[a-zA-Z0-9_.%-]*)["\']?',
    r'href=["\']([^"\']*?/(?:shop|winkel|tienda|boutique|assortiment)(?:/[a-zA-Z0-9_.%-]*)?)["\']?',  # + assortiment (NL)
    r'href=["\']([^"\']*(?:/c/[a-zA-Z0-9_.%-]+)["\']?)',
    r'href=["\']([^"\']*(?:/collections/[a-zA-Z0-9_.%-]+)["\']?)',
    r'href=["\']([^"\']*(?:/browse/[a-zA-Z0-9_.%-]+)["\']?)',
    r'href=["\']([^"\']*(?:/store)(?:/[a-zA-Z0-9_.%-]*)?["\']?)',
    r'href=["\']([^"\']*(?:/catalog/category/view/[a-zA-Z0-9_.%-]+)["\']?)',
]
_PRODUCT_PATTERNS = [
    r'(?:href|data-href)=["\']([^"\']*?/product/[a-zA-Z0-9_.%-]+/?)(?=["\']?)',  # WooCommerce (singular, optional trailing slash)
    r'(?:href|data-href)=["\']([^"\']*?/products?/[a-zA-Z0-9_.%-]+/?)["\']?',
    r'(?:href|data-href)=["\']([^"\']*?/p/[a-zA-Z0-9_.%-]+)["\']?',  # BigCommerce short
    r'href=["\']([^"\']*?/item/[a-zA-Z0-9_.%-]+)["\']?',
    r'href=["\']([^"\']*?/prod(?:uct)?/[a-zA-Z0-9_.%-]+)["\']?',
    r'href=["\']([^"\']*?/catalog/product/view/[a-zA-Z0-9_.%-]+)["\']?',  # Magento
    r'(?:href|data-href)=["\']([^"\']*?/product-page/[a-zA-Z0-9_.%-]+)["\']?',  # Wix
    # BigCommerce root-level product slugs (relative and full URL)
    r'href=["\'](/(?!categories|cart\.|content/|account|shop/)[a-zA-Z0-9][a-zA-Z0-9_.%-]*(?:-[a-zA-Z0-9_.%-]+)+/)["\']?',
    r'href=["\'](https?://[^"\']+/(?!categories|cart\.|content/|account|shop/)[a-zA-Z0-9][a-zA-Z0-9_.%-]*(?:-[a-zA-Z0-9_.%-]+)+/)["\']?',
    r'(https?://[^"\'\s<>]*?/products?/[a-zA-Z0-9_.%-]+|/products?/[a-zA-Z0-9_.%-]+)',
    r'(https?://[^"\'\s<>]*?/p/[a-zA-Z0-9_.%-]+|/p/[a-zA-Z0-9_.%-]+)',
]


def _first_match(html: str, patterns: list[str], base: str) -> str:
    """Return first URL matched by any pattern, made absolute with base. Empty if none."""
    for pat in patterns:
        m = re.search(pat, html, re.I)
        if m:
            raw = m.group(1).split('"')[0].split("'")[0].strip()
            if not raw:
                continue
            if raw.startswith("http"):
                return raw
            return urljoin(base + "/", raw)
    return ""


def _is_valid_product_url(url: str, base: str) -> bool:
    """Return False if url is clearly not a product page (CDN, image/asset, API, or different domain)."""
    if not url or not base:
        return False
    try:
        p_base = urlparse(base)
        p_url = urlparse(url)
        base_netloc = (p_base.netloc or "").lower().lstrip("www.")
        url_netloc = (p_url.netloc or "").lower().lstrip("www.")
        if not base_netloc or not url_netloc:
            return True
        # Reject known CDN/asset hosts
        if "cdn" in url_netloc or "bigcommerce.com" in url_netloc or "shopify.com" in url_netloc:
            return False
        # Reject different domain (allow subdomains of store, e.g. shop.example.com for example.com)
        if base_netloc != url_netloc and not (url_netloc.endswith("." + base_netloc)):
            return False
        path = (p_url.path or "").lower()
        if "/images/" in path or "/stencil/" in path or "/assets/" in path or "/static/" in path:
            return False
        # Reject WordPress API/admin and other non-store pages
        if "/wp-json" in path or "/wp-admin" in path or path.startswith("/feed") or "rest_route" in (path + " " + (p_url.query or "")):
            return False
        # Reject paths that are clearly not product pages (schedule-a-call, contact, results, etc.)
        if _path_looks_like_non_ecommerce(path, "product"):
            return False
        return True
    except Exception:
        return True


def _get_sitemap_text(base: str, *, timeout: int = 10, fast: bool = False) -> str:
    """
    Fetch sitemap content by trying common sitemap URLs.
    If the response is a sitemap index, follow sub-sitemap <loc> URLs and return combined text.
    fast=True: try wp-sitemap.xml and sitemap.xml in parallel, shorter timeouts, max 3 sub-sitemaps in parallel.
    """
    import requests
    headers = {"User-Agent": "Mozilla/5.0 (compatible; Sparksmetrics-CRO-Scan/1.0)"}
    t_first = 2 if fast else timeout
    t_sub = 1.5 if fast else 8
    paths = ("wp-sitemap.xml", "sitemap.xml") if fast else (
        "sitemap.xml", "wp-sitemap.xml", "sitemap_index.xml", "wp-sitemap-index.xml", "sitemap-index.xml"
    )

    def _fetch_one(path: str) -> str:
        url = urljoin(base + "/", path)
        try:
            r = requests.get(url, timeout=t_first, headers=headers)
            if r.status_code == 200 and r.text:
                return (r.text or "").strip()
        except Exception:
            pass
        return ""

    if fast:
        # Parallel: try both sitemap URLs at once, use first successful response
        with ThreadPoolExecutor(max_workers=2) as ex:
            futures = {ex.submit(_fetch_one, p): p for p in paths}
            for fut in as_completed(futures, timeout=t_first + 0.5):
                text = fut.result()
                if not text:
                    continue
                if "<sitemap>" in text.lower():
                    sub_urls = [m.group(1).strip() for m in re.finditer(r"<loc>\s*(https?://[^<]+)\s*</loc>", text, re.I)]
                    def priority(u: str) -> int:
                        u_lower = u.lower()
                        if "product" in u_lower or "taxonomy" in u_lower or "category" in u_lower or "cat-" in u_lower or "assortiment" in u_lower:
                            return 0
                        return 1
                    sub_urls.sort(key=priority)
                    sub_urls = sub_urls[:3]
                    combined = []

                    def _fetch_sub(sub_url: str) -> str:
                        try:
                            r2 = requests.get(sub_url, timeout=t_sub, headers=headers)
                            if r2.status_code == 200 and r2.text:
                                return (r2.text or "")[:300000]
                        except Exception:
                            pass
                        return ""

                    with ThreadPoolExecutor(max_workers=3) as ex2:
                        for part in ex2.map(_fetch_sub, sub_urls):
                            if part:
                                combined.append(part)
                    return "\n".join(combined) if combined else ""
                return text[:500000]
        return ""

    for sitemap_path in paths:
        text = _fetch_one(sitemap_path)
        if not text:
            continue
        if "<sitemap>" in text.lower():
            sub_urls = [m.group(1).strip() for m in re.finditer(r"<loc>\s*(https?://[^<]+)\s*</loc>", text, re.I)]
            def priority(u: str) -> int:
                u_lower = u.lower()
                if "product" in u_lower or "taxonomy" in u_lower or "category" in u_lower or "cat-" in u_lower or "assortiment" in u_lower:
                    return 0
                return 1
            sub_urls.sort(key=priority)
            combined = []
            for sub_url in sub_urls[:15]:
                try:
                    r2 = requests.get(sub_url, timeout=t_sub, headers=headers)
                    if r2.status_code == 200 and r2.text:
                        combined.append((r2.text or "")[:300000])
                except Exception:
                    pass
            return "\n".join(combined) if combined else ""
        return text[:500000]
    return ""


# Path segments that indicate a URL is NOT a real shop category or product page (agency, marketing, contact, etc.)
_NON_ECOMMERCE_COLLECTION_SEGMENTS = frozenset({
    "results", "schedule", "contact", "about", "blog", "pricing", "book", "call", "demo", "audit",
    "ebook", "case-study", "case-studies", "services", "thank-you", "privacy", "terms", "login",
    "signup", "careers", "team", "faq", "support", "help", "webinar", "podcast", "resources",
    "download", "get-started", "request-demo", "book-a-call", "schedule-a-call",
})
_NON_ECOMMERCE_PRODUCT_SEGMENTS = frozenset({
    "schedule-a-call", "book-a-call", "contact-us", "about-us", "get-started", "request-demo",
    "results", "schedule", "contact", "about", "blog", "pricing", "demo", "audit", "ebook",
    "services", "login", "signup", "privacy", "terms", "careers", "team", "faq", "support",
    "help", "webinar", "podcast", "resources", "download", "thank-you", "case-study", "case-studies",
    "guide", "strategies", "strategy", "checklist", "tips", "whitepaper", "report",
})


def _path_looks_like_non_ecommerce(path: str, kind: str) -> bool:
    """Return True if path clearly indicates a non-ecommerce page (e.g. /results/shop, /schedule-a-call/, ...-ebook/)."""
    if not path:
        return False
    segments = [s.lower() for s in path.strip("/").split("/") if s]
    blocklist = _NON_ECOMMERCE_COLLECTION_SEGMENTS if kind == "collection" else _NON_ECOMMERCE_PRODUCT_SEGMENTS
    # Reject if any segment equals or contains a blocklisted term (e.g. "...-ebook" or "schedule-a-call")
    for seg in segments:
        for blocked in blocklist:
            if seg == blocked or blocked in seg:
                return True
    return False


def _url_is_homepage(url: str, base: str) -> bool:
    """True if url normalizes to the same as base (homepage)."""
    if not url or not base:
        return not url and not base
    try:
        a = urlparse(url)
        b = urlparse(base)
        path_a = (a.path or "/").rstrip("/") or "/"
        path_b = (b.path or "/").rstrip("/") or "/"
        return (a.netloc or "").lower().lstrip("www.") == (b.netloc or "").lower().lstrip("www.") and path_a == path_b
    except Exception:
        return False


def _first_match_same_origin(html: str, patterns: list[str], base: str) -> str:
    """Like _first_match but only returns a URL that is same-origin and not a CDN/asset (for product links)."""
    for pat in patterns:
        for m in re.finditer(pat, html, re.I):
            raw = m.group(1).split('"')[0].split("'")[0].strip()
            if not raw:
                continue
            url = raw if raw.startswith("http") else urljoin(base + "/", raw)
            if _is_valid_product_url(url, base):
                return url
    return ""


def _extract_from_sitemap_text(text: str, base: str) -> tuple[str, str]:
    """Extract first valid product URL and first valid category URL from sitemap text (<loc>...</loc>). Returns (product_url, category_url), either may be empty."""
    product_url = ""
    category_url = ""
    if not text:
        return product_url, category_url
    # Product: standard paths
    prod_m = re.search(
        r'<loc>\s*(https?://[^<]*?(?:/product(?:s)?/|/p/|/item/|/catalog/product/view/|/product-page/)[a-zA-Z0-9_.%-/]*)\s*</loc>',
        text, re.I
    )
    if prod_m:
        cand = prod_m.group(1).strip()
        if _is_valid_product_url(cand, base):
            product_url = cand
    if not product_url:
        for m in re.finditer(
            r'<loc>\s*(https?://[^<]+/(?!categories|cart\.|content/|account|shop/)[a-zA-Z0-9][a-zA-Z0-9_.%-]*(?:-[a-zA-Z0-9_.%-]+)+/)\s*</loc>',
            text, re.I
        ):
            cand = m.group(1).strip()
            if _is_valid_product_url(cand, base):
                product_url = cand
                break
    # Category
    cat_m = re.search(
        r'<loc>\s*(https?://[^<]*?(?:'
        r'/product-categor(?:y|ie)/|/categor(?:y|ies|ie|ien|ia|ias)/|/kategor(?:y|ie|ien)/|'
        r'/shop/|/winkel/|/tienda/|/boutique/|/assortiment/|/c/|/collections/|/store/|/browse/|'
        r'/catalog/category/view/|/produkt-kategorie/|/categoria-producto/'
        r')[a-zA-Z0-9_.%-/]*)\s*</loc>',
        text, re.I
    )
    if cat_m:
        cand = cat_m.group(1).strip()
        if not _url_is_homepage(cand, base):
            path = (urlparse(cand).path or "").strip("/")
            if not _path_looks_like_non_ecommerce(path, "collection"):
                category_url = cand
    return product_url, category_url


def discover_pages_generic(store_url: str, *, fast: bool = False) -> dict[str, str]:
    """
    Discover homepage, one category page, and one product page for any ecommerce store.
    fast=True: shorter timeouts, try only 2 sitemap URLs and max 3 sub-sitemaps, skip extra fetches.
    Returns same shape as discover_pages: {"homepage": url, "collection": url, "product": url}.
    """
    from flask import current_app
    import requests

    base = store_url.rstrip("/")
    out: dict[str, str] = {
        "homepage": base,
        "collection": "",
        "product": "",
    }
    t = 2 if fast else 10
    t_secondary = 2 if fast else 8

    # 1) Sitemap first: try common sitemap URLs and extract product/category from <loc> entries
    sitemap_text = _get_sitemap_text(base, fast=fast)
    if sitemap_text:
        product_url, category_url = _extract_from_sitemap_text(sitemap_text, base)
        if product_url:
            out["product"] = product_url
        if category_url:
            out["collection"] = category_url

    # 2) Only scrape frontend when we still need product or collection
    if not out["product"] or not out["collection"]:
        try:
            r = requests.get(
                base,
                timeout=t,
                headers={"User-Agent": "Mozilla/5.0 (compatible; Sparksmetrics-CRO-Scan/1.0)"},
                allow_redirects=True,
            )
            if r.status_code != 200:
                pass
            else:
                html = (r.text or "")[:200000]
                if not out["collection"]:
                    out["collection"] = _first_match(html, _CATEGORY_PATTERNS, base)
                    if out["collection"] and (_url_is_homepage(out["collection"], base) or _path_looks_like_non_ecommerce((urlparse(out["collection"]).path or "").strip("/"), "collection")):
                        out["collection"] = ""
                    if not out["collection"]:
                        for segment in (
                            "product-category/", "product-categorie/", "categorie/", "winkel/",
                            "kategorie/", "categoria/", "collections/", "category/", "shop/", "assortiment/",
                        ):
                            pat = re.compile(
                                r'(https?://[a-zA-Z0-9][a-zA-Z0-9.-]*' + re.escape(segment) + r'[a-zA-Z0-9_.%-/]*)',
                                re.I
                            )
                            m = pat.search(html)
                            if m:
                                raw = m.group(1).strip().split('"')[0].split("'")[0].split(" ")[0].rstrip(".,;)>")
                                if "/product/" in raw and "product-category" not in raw and "product-categorie" not in raw:
                                    continue
                                if not _url_is_homepage(raw, base):
                                    path = (urlparse(raw).path or "").strip("/")
                                    if not _path_looks_like_non_ecommerce(path, "collection"):
                                        out["collection"] = raw
                                        break
                if not out["product"]:
                    out["product"] = _first_match_same_origin(html, _PRODUCT_PATTERNS, base)
                    if not out["product"]:
                        for m in re.finditer(
                            r'(https?://[^"\'\s<>]+/product/[a-zA-Z0-9][a-zA-Z0-9_.%-]*)|(/product/[a-zA-Z0-9][a-zA-Z0-9_.%-]*)',
                            html, re.I
                        ):
                            raw = (m.group(1) or m.group(2) or "").strip().split('"')[0].split("'")[0].split(" ")[0].rstrip(".,;)>")
                            if not raw or "/wp-json" in raw or "/wp-admin" in raw:
                                continue
                            url = raw if raw.startswith("http") else urljoin(base + "/", raw)
                            if _is_valid_product_url(url, base):
                                out["product"] = url
                                break
                if not out["product"] and out["collection"] and not fast:
                    try:
                        r2 = requests.get(out["collection"], timeout=t_secondary, headers={"User-Agent": "Mozilla/5.0 (compatible; Sparksmetrics-CRO-Scan/1.0)"}, allow_redirects=True)
                        if r2.status_code == 200:
                            out["product"] = _first_match_same_origin((r2.text or "")[:150000], _PRODUCT_PATTERNS, base)
                    except Exception:
                        pass
        except Exception as e:
            current_app.logger.warning("CRO scan: generic discovery fetch failed: %s", e)

    if out["product"] and not out["collection"] and not fast:
        try:
            r_prod = requests.get(
                out["product"],
                timeout=t_secondary,
                headers={"User-Agent": "Mozilla/5.0 (compatible; Sparksmetrics-CRO-Scan/1.0)"},
                allow_redirects=True,
            )
            if r_prod.status_code == 200:
                html_prod = (r_prod.text or "")[:200000]
                out["collection"] = _first_match(html_prod, _CATEGORY_PATTERNS, base)
                if out["collection"] and _path_looks_like_non_ecommerce((urlparse(out["collection"]).path or "").strip("/"), "collection"):
                    out["collection"] = ""
                if not out["collection"]:
                    shop_match = re.search(r'href=["\']([^"\']*(?:/shop)(?:/?["\']|\?)', html_prod, re.I)
                    if shop_match:
                        raw = shop_match.group(1).split('"')[0].split("'")[0].strip()
                        cand = raw if raw.startswith("http") else urljoin(base + "/", raw)
                        path = (urlparse(cand).path or "").strip("/")
                        if not _path_looks_like_non_ecommerce(path, "collection"):
                            out["collection"] = cand
        except Exception:
            pass

    if out["product"] and not out["collection"]:
        # Derive collection from product URL parent path when possible (e.g. /bierpakket-bestellen/product-slug/ → /bierpakket-bestellen/)
        try:
            parsed = urlparse(out["product"])
            path = (parsed.path or "").strip("/")
            segments = [s for s in path.split("/") if s]
            if len(segments) >= 2:
                parent_path = "/" + "/".join(segments[:-1]) + "/"
                derived = urljoin(base + "/", parent_path)
                if not _url_is_homepage(derived, base) and not _path_looks_like_non_ecommerce((urlparse(derived).path or "").strip("/"), "collection"):
                    out["collection"] = derived
            # If single-segment product path or derived collection invalid, leave collection empty (don't use homepage)
        except Exception:
            pass
        if not out["collection"]:
            out["collection"] = base  # legacy fallback when derivation not possible

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


def get_screenshot_urls(store_url: str, *, is_shopify: bool = True) -> dict[str, str]:
    """
    Return dict of page_name -> URL for homepage, collection (or category), product.
    When BROWSERLESS_API_TOKEN or SCRAPFLY_API_KEY is set: returns raw page URLs (fetched via that provider in ai_analysis).
    Otherwise: returns thum.io screenshot URLs. Keys: homepage, collection, product.
    For Shopify stores uses discover_pages(); for other ecommerce uses discover_pages_generic() (home, category, product).
    """
    from flask import current_app

    pages = discover_pages(store_url) if is_shopify else discover_pages_generic(store_url)
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
