"""
Gestione mockup surge.sh

  python manage.py list
  python manage.py deploy   <slug>
  python manage.py teardown <slug>
  python manage.py protect  <slug> <password>
  python manage.py unprotect <slug>
  python manage.py serve    <slug>          # locale, porta 8080
  python manage.py add      <slug> <"Nome Cliente"> <dominio>
"""

import json, os, sys, subprocess, hashlib, re, datetime, shutil

REGISTRY = os.path.join(os.path.dirname(__file__), "mockups_registry.json")
MOCKUPS_DIR = os.path.join(os.path.dirname(__file__), "clienti")

PW_MARKER_START = "<!-- PW-GATE-START -->"
PW_MARKER_END   = "<!-- PW-GATE-END -->"

# ── Registry helpers ────────────────────────────────────────────────────────

def load_registry():
    if not os.path.exists(REGISTRY):
        return {}
    with open(REGISTRY, encoding="utf-8") as f:
        return json.load(f)

def save_registry(data):
    with open(REGISTRY, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def get_site(slug):
    reg = load_registry()
    if slug not in reg:
        die(f"Slug '{slug}' non trovato nel registry. Usa 'list' per vedere i siti.")
    return reg, reg[slug]

# ── Surge helpers ───────────────────────────────────────────────────────────

NPX = "npx.cmd" if sys.platform == "win32" else "npx"

def surge_deploy(folder, domain):
    result = subprocess.run(
        [NPX, "--yes", "surge", folder, domain],
        capture_output=False
    )
    return result.returncode == 0

def surge_teardown(domain):
    result = subprocess.run(
        [NPX, "--yes", "surge", "teardown", domain],
        capture_output=False
    )
    return result.returncode == 0

# ── Password gate ───────────────────────────────────────────────────────────

def _sha256_hex(password):
    return hashlib.sha256(password.encode()).hexdigest()

PW_GATE_TEMPLATE = """\
<!-- PW-GATE-START -->
<div id="pw-gate" style="position:fixed;inset:0;z-index:9999;background:#1C1814;display:flex;align-items:center;justify-content:center;font-family:sans-serif;">
  <div style="text-align:center;color:#fff;max-width:320px;width:90%;padding:20px">
    <div style="font-size:1.4rem;margin-bottom:8px;font-weight:600;">Accesso riservato</div>
    <p style="font-size:.85rem;color:rgba(255,255,255,.5);margin-bottom:24px;">Questa è una preview privata.</p>
    <input id="pw-in" type="password" placeholder="Password" onkeydown="if(event.key==='Enter')_chk()" style="width:100%;padding:12px 16px;border:1px solid #B8935A;background:transparent;color:#fff;font-size:1rem;border-radius:4px;outline:none;margin-bottom:10px;box-sizing:border-box;" />
    <button onclick="_chk()" style="width:100%;padding:12px;background:#B8935A;color:#fff;border:none;border-radius:4px;font-size:.9rem;cursor:pointer;letter-spacing:.05em;">Entra</button>
    <div id="pw-err" style="color:#e74c3c;font-size:.8rem;margin-top:8px;visibility:hidden;">Password non corretta</div>
  </div>
</div>
<script>
  (function(){
    const H="{HASH}";
    async function _chk(){
      const v=document.getElementById('pw-in').value;
      const b=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(v));
      const h=Array.from(new Uint8Array(b)).map(x=>x.toString(16).padStart(2,'0')).join('');
      if(h===H){document.getElementById('pw-gate').remove();sessionStorage.setItem('_ok','1');}
      else{document.getElementById('pw-err').style.visibility='visible';}
    }
    window._chk=_chk;
    if(sessionStorage.getItem('_ok')==='1')document.getElementById('pw-gate').remove();
  })();
</script>
<!-- PW-GATE-END -->"""

def inject_password(slug, password):
    index = os.path.join(MOCKUPS_DIR, slug, "index.html")
    with open(index, encoding="utf-8") as f:
        html = f.read()
    remove_password_gate(slug)
    with open(index, encoding="utf-8") as f:
        html = f.read()
    gate = PW_GATE_TEMPLATE.replace("{HASH}", _sha256_hex(password))
    html = html.replace("<body>", "<body>\n" + gate, 1)
    with open(index, "w", encoding="utf-8") as f:
        f.write(html)

def remove_password_gate(slug):
    index = os.path.join(MOCKUPS_DIR, slug, "index.html")
    with open(index, encoding="utf-8") as f:
        html = f.read()
    pattern = re.compile(
        re.escape(PW_MARKER_START) + r".*?" + re.escape(PW_MARKER_END) + r"\n?",
        re.DOTALL
    )
    cleaned = pattern.sub("", html)
    with open(index, "w", encoding="utf-8") as f:
        f.write(cleaned)

# ── Display helpers ─────────────────────────────────────────────────────────

STATUS_ICON = {
    "live":      "[LIVE]      ",
    "teardown":  "[OFFLINE]   ",
    "local":     "[LOCALE]    ",
    "protected": "[PROTETTO]  ",
}

def print_header():
    reg = load_registry()
    n = len(reg)
    print()
    print("=" * 66)
    print(f"  MOCKUP DASHBOARD  -  {n} sito{'i' if n!=1 else ''} registrato{'i' if n!=1 else ''}")
    print("=" * 66)

def print_site(slug, site):
    status = site.get("status", "?")
    icon   = STATUS_ICON.get(status, "❓ " + status.upper())
    domain = site.get("domain", "—")
    name   = site.get("name", slug)
    date   = site.get("deployed_at", "—")
    pw_tag = "  [password attiva]" if site.get("protected") else ""
    print(f"  {icon}  {slug}")
    print(f"     {name}")
    if status in ("live", "protected"):
        print(f"     https://{domain}{pw_tag}")
    elif status == "local":
        print(f"     locale: python manage.py serve {slug}  (porta 8080)")
    print(f"     deployato il {date}")
    print("-" * 66)

def die(msg):
    print(f"\n  ERRORE: {msg}\n")
    sys.exit(1)

# ── Commands ─────────────────────────────────────────────────────────────────

def cmd_list():
    reg = load_registry()
    print_header()
    if not reg:
        print("  Nessun sito registrato.")
        print("=" * 66)
        return
    for slug, site in reg.items():
        print_site(slug, site)
    print()
    print("  Comandi disponibili:")
    print("    python manage.py deploy   <slug>")
    print("    python manage.py teardown <slug>")
    print("    python manage.py protect  <slug> <password>")
    print("    python manage.py unprotect <slug>")
    print("    python manage.py serve    <slug>")
    print()


def cmd_deploy(slug):
    reg, site = get_site(slug)
    folder = os.path.join(MOCKUPS_DIR, slug)
    if not os.path.isdir(folder):
        die(f"Cartella mockup non trovata: {folder}")
    domain = site["domain"]
    print(f"\n  Pubblico {slug} su https://{domain} ...")
    ok = surge_deploy(folder, domain)
    if ok:
        site["status"] = "protected" if site.get("protected") else "live"
        site["deployed_at"] = datetime.date.today().isoformat()
        save_registry(reg)
        print(f"\n  OK  Online: https://{domain}\n")
    else:
        print("\n  ERRORE: Deploy fallito.\n")


def cmd_teardown(slug):
    reg, site = get_site(slug)
    domain = site["domain"]
    print(f"\n  Rimuovo https://{domain} da surge ...")
    ok = surge_teardown(domain)
    if ok:
        site["status"] = "teardown"
        save_registry(reg)
        print(f"\n  OK  Sito rimosso.\n")
    else:
        print("\n  ERRORE: Teardown fallito.\n")


def cmd_protect(slug, password):
    reg, site = get_site(slug)
    folder = os.path.join(MOCKUPS_DIR, slug)
    print(f"\n  Aggiungo password gate a '{slug}' ...")
    inject_password(slug, password)
    domain = site["domain"]
    ok = surge_deploy(folder, domain)
    if ok:
        site["status"] = "protected"
        site["protected"] = True
        save_registry(reg)
        print(f"\n  OK  Sito protetto da password: https://{domain}\n")
    else:
        remove_password_gate(slug)
        print("\n  ERRORE: Deploy fallito. Password gate rimosso dal file locale.\n")


def cmd_unprotect(slug):
    reg, site = get_site(slug)
    folder = os.path.join(MOCKUPS_DIR, slug)
    print(f"\n  Rimuovo password gate da '{slug}' ...")
    remove_password_gate(slug)
    domain = site["domain"]
    ok = surge_deploy(folder, domain)
    if ok:
        site["status"] = "live"
        site["protected"] = False
        save_registry(reg)
        print(f"\n  OK  Password rimossa: https://{domain}\n")
    else:
        print("\n  ERRORE: Deploy fallito.\n")


def cmd_serve(slug):
    reg, site = get_site(slug)
    folder = os.path.join(MOCKUPS_DIR, slug)
    if not os.path.isdir(folder):
        die(f"Cartella non trovata: {folder}")
    if site.get("status") in ("live", "protected"):
        print(f"\n  AVVISO: Il sito e' ancora attivo su surge: https://{site['domain']}")
        print("     Usa prima 'teardown' se vuoi rimuoverlo dalla rete.\n")
    site["status"] = "local"
    save_registry(reg)
    port = 8080
    print(f"\n  Serving '{slug}' in locale su http://localhost:{port}")
    print("  Premi Ctrl+C per fermare.\n")
    os.chdir(folder)
    import http.server
    handler = http.server.SimpleHTTPRequestHandler
    with http.server.HTTPServer(("", port), handler) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n  Server fermato.\n")


def cmd_add(slug, name, domain):
    reg = load_registry()
    if slug in reg:
        die(f"'{slug}' esiste già nel registry.")
    reg[slug] = {
        "name": name,
        "domain": domain,
        "deployed_at": datetime.date.today().isoformat(),
        "status": "teardown",
        "protected": False,
    }
    save_registry(reg)
    print(f"\n  OK  '{slug}' aggiunto al registry (status: offline).")
    print(f"     Usa 'deploy {slug}' per pubblicarlo.\n")


# ── Main ──────────────────────────────────────────────────────────────────────

USAGE = """
Uso: python manage.py <comando> [argomenti]

  list                          — mostra tutti i siti
  deploy   <slug>               — pubblica su surge
  teardown <slug>               — rimuove da surge
  protect  <slug> <password>    — aggiunge password e redeploya
  unprotect <slug>              — rimuove password e redeploya
  serve    <slug>               — serve in locale su porta 8080
  add      <slug> "Nome" dominio — registra un nuovo sito

Esempio:
  python manage.py protect nuova-immagine segreta123
"""

if __name__ == "__main__":
    args = sys.argv[1:]
    if not args or args[0] in ("help", "--help", "-h"):
        print(USAGE)
    elif args[0] == "list":
        cmd_list()
    elif args[0] == "deploy" and len(args) == 2:
        cmd_deploy(args[1])
    elif args[0] == "teardown" and len(args) == 2:
        cmd_teardown(args[1])
    elif args[0] == "protect" and len(args) == 3:
        cmd_protect(args[1], args[2])
    elif args[0] == "unprotect" and len(args) == 2:
        cmd_unprotect(args[1])
    elif args[0] == "serve" and len(args) == 2:
        cmd_serve(args[1])
    elif args[0] == "add" and len(args) == 4:
        cmd_add(args[1], args[2], args[3])
    else:
        print(USAGE)
