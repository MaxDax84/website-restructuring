"""
Pipeline: URL sito originale -> mockup HTML completo

Architettura:
  Scraping profondo -> manifesto contenuti strutturato
  Call 1 (CSS):  brand CSS dal colori originali (~150 righe)
  Call 2 (HTML): HTML body COMPLETO con TUTTI i contenuti del manifesto
  Continuation loop: fino a 3 tentativi se troncato
"""

import os, re, json, requests
from io import BytesIO
from urllib.parse import urljoin, quote_plus
from bs4 import BeautifulSoup
from PIL import Image
from dotenv import load_dotenv

load_dotenv()

HEADERS  = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0"}
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CLIENTI  = os.path.join(BASE_DIR, "clienti")

PRICE_IN  = 3.00
PRICE_OUT = 15.00


# ── Scraping profondo ─────────────────────────────────────────────────────────

def _fetch(url):
    if not url.startswith("http"):
        url = "https://" + url
    try:
        r = requests.get(url, headers=HEADERS, timeout=15, allow_redirects=True)
        r.raise_for_status()
        return r.text, r.url
    except Exception as e:
        return None, str(e)


def _clean_html(html):
    """HTML senza script/style, max 40000 caratteri."""
    soup = BeautifulSoup(html, "html.parser")
    for t in soup(["script", "style", "noscript", "svg", "iframe", "link", "meta"]):
        t.decompose()
    return soup.prettify()[:40000]


def _build_manifest(html, final_url):
    """
    Estrae TUTTO il contenuto del sito in forma strutturata:
    titolo, sezioni con heading + testi + liste, contatti, prezzi.
    Questo diventa la checklist obbligatoria per Claude.
    """
    soup = BeautifulSoup(html, "html.parser")
    for t in soup(["script", "style", "noscript", "svg", "iframe"]):
        t.decompose()

    manifest = {"sections": [], "contacts": {}, "prices": []}

    # --- Sezioni principali: ogni h2/h3 con tutto il suo contenuto ---
    seen_headings = set()
    for heading_tag in soup.find_all(["h1", "h2", "h3"]):
        heading_text = heading_tag.get_text(strip=True)
        if not heading_text or heading_text in seen_headings or len(heading_text) < 3:
            continue
        seen_headings.add(heading_text)

        # Raccoglie tutti i testi nel blocco genitore
        parent = heading_tag.parent
        texts, items = [], []
        for el in parent.find_all(["p", "span", "div"], recursive=False):
            t = el.get_text(separator=" ", strip=True)
            if len(t) > 15 and t not in texts:
                texts.append(t[:300])
        for li in parent.find_all("li"):
            t = li.get_text(strip=True)
            if len(t) > 3 and t not in items:
                items.append(t[:200])

        # Se il parent ha poco, prova anche il nonno
        if not texts and not items:
            grandparent = parent.parent if parent.parent else parent
            for el in grandparent.find_all(["p", "li"]):
                t = el.get_text(separator=" ", strip=True)
                if len(t) > 15:
                    texts.append(t[:300])

        section = {"heading": heading_text, "level": heading_tag.name}
        if texts:
            section["texts"] = texts[:8]
        if items:
            section["items"] = items[:15]
        manifest["sections"].append(section)

    # --- Contatti ---
    plain = soup.get_text(separator=" ", strip=True)
    phone_m = re.search(r'(\+39[\s\-]?)?0\d[\d\s\-\.]{5,12}\d', plain)
    if phone_m:
        raw = re.sub(r'[\s\-\.]', '', phone_m.group(0))
        manifest["contacts"]["phone_raw"]     = raw
        manifest["contacts"]["phone_display"] = re.sub(r'(\d{2,3})(\d{3,4})(\d{3,4})', r'\1 \2 \3', raw)

    email_m = re.search(r'href=["\']mailto:([^"\'?]+)', html, re.IGNORECASE)
    if email_m:
        manifest["contacts"]["email"] = email_m.group(1).strip()

    addr_m = re.search(r'(via|viale|piazza|corso|largo)\s+[A-Za-z\xc0-\xff\s\.]+?\d+', plain, re.IGNORECASE)
    if addr_m:
        manifest["contacts"]["address"] = addr_m.group(0).strip()

    zip_m = re.search(r'\b(\d{5})\s+([A-Za-z\xc0-\xff]+)', plain)
    if zip_m:
        manifest["contacts"]["zip"]  = zip_m.group(1)
        manifest["contacts"]["city"] = zip_m.group(2).capitalize()

    year_m = re.search(r'(?:dal|since|fondat\w*\s+nel)\s+(1[89]\d{2}|20[01]\d)', plain, re.IGNORECASE)
    if year_m:
        manifest["contacts"]["year_founded"] = year_m.group(1)

    # --- Prezzi ---
    for el in soup.find_all(text=re.compile(r'€|\bprezzo\b|\bda\s+\d', re.I)):
        t = el.strip()
        if 3 < len(t) < 120:
            manifest["prices"].append(t)
    manifest["prices"] = list(dict.fromkeys(manifest["prices"]))[:20]

    # --- Colori CSS dal sito ---
    css_colors = list(dict.fromkeys(re.findall(r'#(?:[0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b', html)))[:10]
    manifest["css_colors"] = css_colors

    return manifest


def scrape_full(url):
    html, final_url = _fetch(url)
    if html is None:
        return None, {"error": final_url}, []

    html_clean = _clean_html(html)
    manifest   = _build_manifest(html, final_url)

    # Immagini
    soup = BeautifulSoup(html, "html.parser")
    image_urls = []
    for img in soup.find_all("img"):
        for attr in ("src", "data-src", "data-lazy-src", "data-original"):
            src = img.get(attr, "")
            if src:
                full = urljoin(final_url, src)
                if full.startswith("http"):
                    image_urls.append(full)
        for part in (img.get("srcset") or "").split(","):
            u = part.strip().split(" ")[0]
            if u.startswith("http"):
                image_urls.append(u)
    image_urls = list(dict.fromkeys(image_urls))

    return html_clean, manifest, image_urls


# ── Download immagini ─────────────────────────────────────────────────────────

def download_images(image_urls, dest_folder, max_images=15):
    os.makedirs(dest_folder, exist_ok=True)
    saved, idx = [], 1
    for url in image_urls:
        if idx > max_images:
            break
        try:
            r = requests.get(url, headers=HEADERS, timeout=10)
            if r.status_code != 200 or len(r.content) < 8_000:
                continue
            img = Image.open(BytesIO(r.content)).convert("RGB")
            if img.width < 200 or img.height < 150:
                continue
            img.thumbnail((1400, 1000), Image.LANCZOS)
            fname = f"img-{idx:02d}.webp"
            img.save(os.path.join(dest_folder, fname), "WEBP", quality=83, method=6)
            saved.append({"file": fname, "w": img.width, "h": img.height})
            idx += 1
        except Exception:
            continue
    return saved


# ── Call 1: CSS ───────────────────────────────────────────────────────────────

CSS_SYSTEM = """\
Sei un web designer. Genera SOLO il codice CSS per il restyling di un sito locale italiano.
- Usa CSS custom properties per tutti i colori del brand
- Compatto ma completo: copri nav, hero, sezioni card, pricing, gallery, contatti, footer, modal
- html { scroll-behavior: smooth; } obbligatorio
- Responsive mobile-first con media queries
- Rispondi SOLO con CSS puro, senza tag <style>\
"""

def _gen_css(client, manifest, category):
    colors = ", ".join(manifest.get("css_colors", [])[:6]) or "da definire"
    city   = manifest.get("contacts", {}).get("city", "")
    prompt = (
        f"Categoria: {category}\n"
        f"Citta': {city}\n"
        f"Colori estratti dal sito originale: {colors}\n\n"
        "Genera CSS completo ispirato ai colori del brand originale."
    )
    resp = client.messages.create(
        model="claude-sonnet-4-6", max_tokens=3000,
        system=CSS_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    )
    css = resp.content[0].text.strip()
    css = re.sub(r'^```css\s*', '', css, re.DOTALL)
    css = re.sub(r'```\s*$',    '', css, re.DOTALL)
    return css, resp.usage.input_tokens, resp.usage.output_tokens


# ── Call 2: HTML body ─────────────────────────────────────────────────────────

HTML_SYSTEM = """\
Sei un web designer senior. Devi produrre il NUOVO sito web di un'attivita' locale italiana: \
una versione moderna e professionale che mantiene FEDELMENTE la struttura e i contenuti \
del sito originale.

REGOLA FONDAMENTALE: il manifesto dei contenuti e' la tua UNICA fonte di verita'.
Ogni voce del manifesto (sezione, testo, lista, prezzo) DEVE comparire nel tuo output.
Non omettere, non riassumere, non inventare. Usa i testi originali parola per parola.

STRUTTURA:
- Riproduci TUTTE le sezioni del sito originale con i loro nomi esatti
- Ordine identico a quello del sito originale
- Una sola pagina HTML con smooth scroll (anchor link nel nav verso ogni sezione)
- Usa tutte le immagini disponibili distribuite nelle sezioni appropriate

TECNICO:
- File HTML completo: <!DOCTYPE html> ... </html>
- CSS fornito nel <head> dentro <style>
- <meta name="robots" content="noindex,nofollow">
- Schema.org JSON-LD per il tipo di attivita'
- Modal telefono: ogni click su "Prenota/Chiama/Contatta" apre modal con numero cliccabile
- Rispondi SOLO con il codice HTML completo\
"""

def _gen_html(client, html_clean, manifest, images_info, category, css):
    img_list = "\n".join(
        f"  img/{i['file']} ({i['w']}x{i['h']}px)"
        for i in images_info
    ) or "  (nessuna immagine)"

    manifest_str = json.dumps(manifest, ensure_ascii=False, indent=2)

    prompt = f"""\
## MANIFESTO DEI CONTENUTI ORIGINALI (checklist obbligatoria — includi TUTTO)
```json
{manifest_str}
```

## IMMAGINI DISPONIBILI (usale TUTTE distribuendole nelle sezioni)
{img_list}

## CATEGORIA
{category}

## CSS GIA' GENERATO (includilo nel <head> dentro <style>)
```css
{css}
```

## HTML DEL SITO ORIGINALE (riferimento per struttura e contenuti aggiuntivi)
```html
{html_clean}
```

Genera il file HTML COMPLETO. Verifica che ogni sezione del manifesto sia presente \
prima di chiudere il tag </html>."""

    total_in, total_out = 0, 0

    # Prima chiamata
    resp = client.messages.create(
        model="claude-sonnet-4-6", max_tokens=8192,
        system=HTML_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    )
    html = resp.content[0].text.strip()
    html = re.sub(r'^```html\s*', '', html, re.DOTALL)
    html = re.sub(r'```\s*$',     '', html, re.DOTALL)
    total_in  += resp.usage.input_tokens
    total_out += resp.usage.output_tokens

    # Loop continuazione (max 3x)
    messages = [
        {"role": "user",      "content": prompt},
        {"role": "assistant", "content": resp.content[0].text},
    ]
    for _ in range(3):
        if '</html>' in html.lower():
            break
        messages.append({
            "role": "user",
            "content": "Il codice e' incompleto. Continua esattamente da dove si e' interrotto "
                       "fino a </html>. Ricorda di includere tutte le sezioni del manifesto."
        })
        r2 = client.messages.create(
            model="claude-sonnet-4-6", max_tokens=4096,
            system=HTML_SYSTEM, messages=messages,
        )
        cont = r2.content[0].text.strip()
        html      += "\n" + cont
        total_in  += r2.usage.input_tokens
        total_out += r2.usage.output_tokens
        messages.append({"role": "assistant", "content": cont})

    return html, total_in, total_out


# ── Generazione template locale (no API) ─────────────────────────────────────

def _gen_template_html(slug, name, url, category):
    """Fallback locale: usa Jinja2 con il template base."""
    from jinja2 import Environment, FileSystemLoader
    tmpl_dir = os.path.join(BASE_DIR, "templates")
    if not os.path.isdir(tmpl_dir):
        raise FileNotFoundError("Cartella templates/ non trovata.")
    html_clean, manifest, image_urls = scrape_full(url)
    img_folder = os.path.join(CLIENTI, slug, "img")
    images_info = download_images(image_urls, img_folder)

    # Import del build_context dal vecchio sistema se presente
    try:
        from generator import build_context, render_mockup
        context = build_context(manifest, name, category, images_info)
        html = render_mockup(context)
    except Exception:
        html = (
            f"<!DOCTYPE html><html lang='it'><head><meta charset='UTF-8'/>"
            f"<title>{name}</title></head><body><h1>{name}</h1>"
            f"<p>Template generato localmente.</p></body></html>"
        )

    with open(os.path.join(CLIENTI, slug, "index.html"), "w", encoding="utf-8") as f:
        f.write(html)
    with open(os.path.join(CLIENTI, slug, "robots.txt"), "w", encoding="utf-8") as f:
        f.write("User-agent: *\nDisallow: /\n")


# ── Stima complessità (senza chiamare Claude) ─────────────────────────────────

def estimate_complexity(url):
    """
    Scrapa il sito e restituisce la stima di costo con range ±20%.

    Calibrazione basata su dati reali:
      - CSS call output:  ~2500 token (consistente)
      - HTML output:      ~1200 token per sezione + 1500 overhead
      - Input HTML call:  (manifest_chars + html_chars) / 4 + 600
      - Input CSS call:   ~400 token
    """
    html_clean, manifest, image_urls = scrape_full(url)
    if html_clean is None:
        return {"error": manifest.get("error", "Sito non raggiungibile")}

    n_sec = len(manifest.get("sections", []))
    n_img = len(image_urls)
    name  = manifest.get("contacts", {}).get("name", "")
    city  = manifest.get("contacts", {}).get("city", "")

    # --- Stima token output ---
    css_out  = 2500                               # Call 1: CSS brand
    html_out = n_sec * 1200 + 1500                # Call 2: HTML body
    html_out = min(html_out, 8192 + 3 * 4096)     # cap a 3 continuazioni max
    total_out = css_out + html_out

    # --- Stima token input ---
    manifest_chars = len(json.dumps(manifest))
    html_chars     = len(html_clean)
    css_in   = 400
    html_in  = (manifest_chars + html_chars) // 4 + 600
    total_in = css_in + html_in

    # --- Costo stimato (±20-25% di variazione reale) ---
    cost_est = round((total_in / 1_000_000 * PRICE_IN) + (total_out / 1_000_000 * PRICE_OUT), 3)

    if n_sec <= 6:
        level = "semplice"
    elif n_sec <= 14:
        level = "medio"
    else:
        level = "complesso"

    return {
        "name":       name,
        "city":       city,
        "sections":   n_sec,
        "images":     n_img,
        "cost_est":   cost_est,
        "level":      level,
        "manifest":   manifest,
        "image_urls": image_urls,
        "html_clean": html_clean,
    }


# ── Pipeline principale ───────────────────────────────────────────────────────

def run_pipeline(slug, name, url, category, domain, on_step=None):
    def step(msg):
        if on_step:
            on_step(msg)

    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        return False, "ANTHROPIC_API_KEY mancante nel .env", 0.0

    import anthropic
    client = anthropic.Anthropic(api_key=api_key)

    folder     = os.path.join(CLIENTI, slug)
    img_folder = os.path.join(folder, "img")
    os.makedirs(img_folder, exist_ok=True)

    total_in, total_out = 0, 0

    # 1. Scraping
    step("Analisi del sito originale...")
    html_clean, manifest, image_urls = scrape_full(url)
    if html_clean is None:
        return False, f"Sito non raggiungibile: {manifest.get('error','')}", 0.0

    if name and len(name) > 2:
        manifest.setdefault("contacts", {})["name"] = name

    n_sections = len(manifest.get("sections", []))
    step(f"Trovate {n_sections} sezioni e {len(image_urls)} immagini nel sito originale.")

    # 2. Immagini
    step("Scarico e ottimizzo le immagini...")
    images_info = download_images(image_urls, img_folder)
    step(f"{len(images_info)} immagini salvate.")

    # 3. CSS
    step("Generazione CSS brand...")
    try:
        css, in1, out1 = _gen_css(client, manifest, category)
        total_in += in1; total_out += out1
        step(f"CSS generato ({out1} token).")
    except Exception as e:
        return False, f"Errore CSS: {e}", 0.0

    # 4. HTML
    step(f"Generazione HTML ({n_sections} sezioni da riprodurre)...")
    try:
        html, in2, out2 = _gen_html(client, html_clean, manifest, images_info, category, css)
        total_in += in2; total_out += out2
        has_body = '<body'    in html.lower()
        closed   = '</html>' in html.lower()
        sections = html.lower().count('<section')
        step(f"HTML generato ({out2} token — {sections} sezioni, chiuso={closed}).")
    except Exception as e:
        return False, f"Errore HTML: {e}", 0.0

    if not has_body:
        return False, "HTML generato senza body — riprova.", 0.0

    # 5. Salva
    step("Salvo i file...")
    with open(os.path.join(folder, "index.html"), "w", encoding="utf-8") as f:
        f.write(html)
    with open(os.path.join(folder, "robots.txt"), "w", encoding="utf-8") as f:
        f.write("User-agent: *\nDisallow: /\n")

    cost = (total_in / 1_000_000 * PRICE_IN) + (total_out / 1_000_000 * PRICE_OUT)
    return True, "", cost
