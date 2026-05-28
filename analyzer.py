import re
import requests
from urllib.parse import urlparse

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

# Domains where the business doesn't own the site — social profiles, booking aggregators
NO_WEBSITE_DOMAINS = {
    "instagram.com", "facebook.com", "fb.com",
    "uala.it", "fresha.com", "vagaro.com",
    "yelp.com", "tripadvisor.com", "tripadvisor.it",
    "google.com", "maps.app.goo.gl",
    "linktr.ee", "linktree.com",
    "tiktok.com", "twitter.com", "x.com",
}

# If any of these keywords appears anywhere in the domain, it's an aggregator
AGGREGATOR_KEYWORDS = [
    "treatwell", "booksy", "uala", "fresha", "vagaro",
    "instagram", "facebook", "tripadvisor",
]

MODERN_SIGNALS = [
    r"bootstrap[- /]?[45]",
    r"tailwindcss|tailwind\.min",
    r"vue\.js|vuejs|react\.min|angular\.min",
]

INTEGRATION_PATTERNS = {
    "Calendly":    r"calendly\.com",
    "Booksy":      r"booksy\.com",
    "TheFork":     r"thefork\.(com|it)|restorando\.com",
    "Google Maps": r"maps\.google\.com|google\.com/maps|maps\.googleapis\.com",
    "OpenTable":   r"opentable\.(com|it)",
    "Doctoralia":  r"doctoralia\.(com|it)",
}

TECH_PATTERNS = {
    "WordPress":   r"/wp-content/|/wp-includes/",
    "Wix":         r"wix\.com|wixsite\.com|wixstatic\.com",
    "Squarespace": r"squarespace\.com|sqsp\.net",
    "Joomla":      r"/components/com_|/administrator/",
    "Drupal":      r"/sites/default/files/|drupal\.js",
    "Webflow":     r"webflow\.io|webflow\.com",
    "Jimdo":       r"jimdo\.com",
    "Weebly":      r"weebly\.com",
}


def fetch_html(url: str) -> tuple:
    if not url.startswith("http"):
        url = "https://" + url
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10, allow_redirects=True)
        resp.raise_for_status()
        return resp.text, resp.url
    except requests.exceptions.SSLError:
        try:
            url_http = url.replace("https://", "http://")
            resp = requests.get(url_http, headers=HEADERS, timeout=10, allow_redirects=True)
            return resp.text, resp.url
        except Exception as e:
            return None, str(e)
    except Exception as e:
        return None, str(e)


def is_aggregator_url(url: str) -> tuple:
    """Returns (True, domain) if the URL is a social profile or booking aggregator."""
    try:
        domain = urlparse(url).netloc.lower().lstrip("www.")
    except Exception:
        return False, ""

    # Exact domain match
    if domain in NO_WEBSITE_DOMAINS:
        return True, domain

    # Subdomain of known aggregator (e.g. hairandrelax.mytreatwell.it)
    for kw in AGGREGATOR_KEYWORDS:
        if kw in domain:
            return True, domain

    return False, ""


def check_login(html: str) -> tuple:
    """Returns (True, reason) if a login/reserved area is detected."""
    patterns = [
        (r'href=["\'][^"\']*/(login|signin|accedi|accesso|area-riservata|area-clienti|my-account)["\']',
         "link login/area riservata"),
        (r'<input[^>]+type=["\']password["\']',
         "campo password"),
    ]
    for pat, label in patterns:
        if re.search(pat, html, re.IGNORECASE):
            return True, label
    return False, ""


def check_ecommerce(html: str) -> tuple:
    """
    Two-tier e-commerce check to avoid false positives.

    Tier 1 — Platform identification (definitive, one hit = discard):
      Requires unambiguous platform-specific patterns, not just the word in a CSS comment.

    Tier 2 — Behavioral signals (need 2+ independent hits):
      Checks actual HTML context (tags, hrefs, classes), not raw text or JSON blobs.
    """

    # --- Tier 1: Platform scripts / markup ---

    # WooCommerce: plugin path in src, or active WC classes/functions (not CSS comments)
    if re.search(r"plugins/woocommerce/assets", html, re.IGNORECASE):
        return True, "WooCommerce (plugin assets)"
    if re.search(r'class=["\'][^"\']*\bwoocommerce\b', html, re.IGNORECASE):
        return True, "WooCommerce (classe HTML)"
    if re.search(r"\bwc[-_]add[-_]to[-_]cart\b|woocommerce-cart\.php", html, re.IGNORECASE):
        return True, "WooCommerce (cart)"

    # Shopify
    if re.search(r"cdn\.shopify\.com|shopify\.com/s/files|Shopify\.theme", html, re.IGNORECASE):
        return True, "Shopify"

    # Wix Store (not just generic Wix, but specifically the store/e-commerce module)
    if re.search(r"wixstores|wix-stores|wix\.com.*addToCart|wixStores", html):
        return True, "Wix Store"

    # Magento
    if re.search(r"Mage\.Cookies|varien/form\.js|skin/frontend/base/default", html, re.IGNORECASE):
        return True, "Magento"

    # OpenCart
    if re.search(r"catalog/view/theme.*\.js|openCart\b", html, re.IGNORECASE):
        return True, "OpenCart"

    # PrestaShop
    if re.search(r"/themes/[^/]+/assets/.*prestashop|prestashop.*blockcart", html, re.IGNORECASE):
        return True, "PrestaShop"

    # --- Tier 2: Behavioral signals (need 2+) ---
    signals = []

    # Actual cart/checkout nav links (in <a href="...">, not in JS strings)
    if re.search(
        r'<a\b[^>]+href=["\'][^"\']*/(cart|carrello|checkout|acquisto)["\']',
        html, re.IGNORECASE
    ):
        signals.append("link carrello/checkout")

    # Add-to-cart buttons or links (in actual HTML tags, not inside JS/JSON)
    # Match only when the pattern is in a tag attribute, not inside a quoted string block
    if re.search(
        r'(?:<button|<input|<a)\b[^>]*(?:add[_-]to[_-]cart|aggiungi[_-]al[_-]carrello)',
        html, re.IGNORECASE
    ):
        signals.append("pulsante add-to-cart")

    # Product URL in actual hrefs
    if re.search(
        r'<a\b[^>]+href=["\'][^"\']*/(prodotto|prodotti|products?)/[^"\']+["\']',
        html, re.IGNORECASE
    ):
        signals.append("URL prodotti")

    # Multiple price-class elements (product listings, not a single price on a services page)
    price_els = re.findall(
        r'<[^>]+class=["\'][^"\']*(?:price|prezzo)[^"\']*["\'][^>]*>[^<]*[€$£\d]',
        html, re.IGNORECASE
    )
    if len(price_els) >= 3:
        signals.append(f"prezzi multipli ({len(price_els)}x)")

    # Product grid container
    if re.search(
        r'class=["\'][^"\']*\b(products-grid|product-list|product-grid|shop-products|product-loop)\b',
        html, re.IGNORECASE
    ):
        signals.append("griglia prodotti")

    if len(signals) >= 2:
        return True, "E-commerce: " + ", ".join(signals)

    return False, ""


def check_modern(html: str) -> tuple:
    has_viewport = bool(re.search(
        r'<meta[^>]+name=["\']viewport["\']', html, re.IGNORECASE
    ))
    modern_framework = any(
        re.search(p, html, re.IGNORECASE) for p in MODERN_SIGNALS
    )
    if has_viewport and modern_framework:
        return True, "Sito gia moderno e responsive"
    return False, ""


def detect_technology(html: str, url: str) -> str:
    combined = html + url
    for tech, pattern in TECH_PATTERNS.items():
        if re.search(pattern, combined, re.IGNORECASE):
            return tech
    return "HTML/CSS"


def detect_integrations(html: str) -> tuple:
    booking = {"Calendly", "Booksy", "TheFork", "OpenTable", "Doctoralia"}
    found = [name for name, pat in INTEGRATION_PATTERNS.items()
             if re.search(pat, html, re.IGNORECASE)]
    return any(i in booking for i in found), found


_EMAIL_RE = re.compile(
    r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}',
    re.IGNORECASE,
)

# Domains that are never real contact emails
_EMAIL_BLACKLIST = {
    "sentry.io", "wix.com", "wordpress.org", "wordpress.com",
    "google.com", "facebook.com", "instagram.com", "jquery.com",
    "example.com", "schema.org", "w3.org", "cloudflare.com",
}


def _is_valid_email(email: str) -> bool:
    domain = email.split("@")[-1].lower()
    if domain in _EMAIL_BLACKLIST:
        return False
    # Skip image/asset filenames that contain @
    if re.search(r'\.(png|jpg|gif|svg|css|js|woff)$', domain):
        return False
    return True


def extract_email(html: str, base_url: str) -> str:
    """Try to find a contact email: mailto links first, then text, then /contatti page."""
    # 1. mailto: links (most reliable — intentionally placed)
    for m in re.finditer(r'href=["\']mailto:([^"\'?]+)', html, re.IGNORECASE):
        email = m.group(1).strip()
        if _EMAIL_RE.match(email) and _is_valid_email(email):
            return email

    # 2. Email pattern anywhere in the HTML text
    for m in _EMAIL_RE.finditer(html):
        email = m.group(0)
        if _is_valid_email(email):
            return email

    # 3. Try the contact page
    from urllib.parse import urljoin
    for slug in ("/contatti", "/contatti/", "/contact", "/contact-us", "/chi-siamo"):
        contact_url = urljoin(base_url, slug)
        try:
            resp = requests.get(contact_url, headers=HEADERS, timeout=8, allow_redirects=True)
            if resp.status_code == 200:
                contact_html = resp.text
                for m in re.finditer(r'href=["\']mailto:([^"\'?]+)', contact_html, re.IGNORECASE):
                    email = m.group(1).strip()
                    if _EMAIL_RE.match(email) and _is_valid_email(email):
                        return email
                for m in _EMAIL_RE.finditer(contact_html):
                    email = m.group(0)
                    if _is_valid_email(email):
                        return email
        except Exception:
            continue

    return ""


def score_site(html: str, url: str) -> int:
    """1–10: higher = older/uglier = better prospect."""
    score = 0

    if not re.search(r'<meta[^>]+name=["\']viewport["\']', html, re.IGNORECASE):
        score += 3  # not mobile-friendly at all

    if url.startswith("http://"):
        score += 2  # no HTTPS

    if len(re.findall(r"<table", html, re.IGNORECASE)) > 3:
        score += 2  # table-based layout

    if re.search(r"©\s*(?:19\d{2}|200\d|201[0-8])", html):
        score += 1  # old copyright year

    if not re.search(r"bootstrap|foundation|bulma|tailwind|materialize", html, re.IGNORECASE):
        score += 1  # no CSS framework

    if re.search(r"\.swf|flashplayer|shockwave", html, re.IGNORECASE):
        score += 2  # Flash

    if len(re.findall(r'style=["\']', html, re.IGNORECASE)) > 20:
        score += 1  # heavy inline styles

    return min(score, 10)


def analyze(url: str) -> dict:
    if not url:
        return {
            "discard": True, "discard_reason": "Nessun sito web",
            "technology": "", "has_bookings": False, "integrations": [],
            "score": 0, "note": "Nessun sito web",
        }

    # Social media profiles and booking aggregators
    agg, domain = is_aggregator_url(url)
    if agg:
        return {
            "discard": True,
            "discard_reason": f"Profilo social/aggregatore ({domain})",
            "technology": "", "has_bookings": False, "integrations": [],
            "score": 0, "note": f"Nessun sito proprio ({domain})",
        }

    html, final_url = fetch_html(url)
    if html is None:
        return {
            "discard": True, "discard_reason": "Sito non raggiungibile",
            "technology": "", "has_bookings": False, "integrations": [],
            "score": 0, "note": f"Errore: {final_url}",
        }

    # Re-check aggregator after redirect (e.g. a domain that redirects to Wix booking)
    agg, domain = is_aggregator_url(final_url)
    if agg:
        return {
            "discard": True,
            "discard_reason": f"Redirect ad aggregatore ({domain})",
            "technology": "", "has_bookings": False, "integrations": [],
            "score": 0, "note": f"Redirect a {domain}",
        }

    # Login / reserved area
    has_login, login_reason = check_login(html)
    if has_login:
        return {
            "discard": True, "discard_reason": f"Login: {login_reason}",
            "technology": detect_technology(html, final_url),
            "has_bookings": False, "integrations": [],
            "score": 0, "note": f"Login: {login_reason}",
        }

    # E-commerce (two-tier)
    is_ecom, ecom_reason = check_ecommerce(html)
    if is_ecom:
        return {
            "discard": True, "discard_reason": ecom_reason,
            "technology": detect_technology(html, final_url),
            "has_bookings": False, "integrations": [],
            "score": 0, "note": ecom_reason,
        }

    # Already modern site
    is_modern, modern_reason = check_modern(html)
    if is_modern:
        return {
            "discard": True, "discard_reason": modern_reason,
            "technology": detect_technology(html, final_url),
            "has_bookings": False, "integrations": [],
            "score": 0, "note": modern_reason,
        }

    technology = detect_technology(html, final_url)
    has_bookings, integrations = detect_integrations(html)
    score = score_site(html, final_url)
    email = extract_email(html, final_url)

    notes = []
    if not re.search(r'<meta[^>]+name=["\']viewport["\']', html, re.IGNORECASE):
        notes.append("Non mobile-friendly")
    if final_url.startswith("http://"):
        notes.append("No HTTPS")
    if integrations:
        notes.append("Embed: " + ", ".join(integrations))

    return {
        "discard": False,
        "discard_reason": "",
        "technology": technology,
        "has_bookings": has_bookings,
        "integrations": integrations,
        "score": score,
        "email": email,
        "note": "; ".join(notes) if notes else "OK",
    }
