"""
Avvia la dashboard + tunnel ngrok pubblico.
Uso: python dashboard_online.py

Prima volta: ti chiede l'authtoken di ngrok (ngrok.com → free signup).
Il token viene salvato nel .env e non ti viene più chiesto.
"""

import os, sys, threading, webbrowser, qrcode
from dotenv import load_dotenv, set_key

load_dotenv()

ENV_FILE = os.path.join(os.path.dirname(__file__), ".env")

# ── Authtoken ─────────────────────────────────────────────────────────────────

def ensure_authtoken():
    token = os.getenv("NGROK_AUTHTOKEN", "").strip()
    if token:
        return token

    print()
    print("=" * 60)
    print("  NGROK — primo avvio")
    print("=" * 60)
    print("  Serve un account ngrok gratuito per il tunnel.")
    print("  1. Vai su https://ngrok.com e registrati (gratis)")
    print("  2. Copia il tuo authtoken da:")
    print("     https://dashboard.ngrok.com/get-started/your-authtoken")
    print()
    token = input("  Incolla qui il tuo authtoken: ").strip()
    if not token:
        print("  Authtoken non inserito. Uscita.")
        sys.exit(1)

    set_key(ENV_FILE, "NGROK_AUTHTOKEN", token)
    os.environ["NGROK_AUTHTOKEN"] = token
    print("  Token salvato nel .env — non ti verra' piu' chiesto.")
    print()
    return token


# ── QR code nel terminale ─────────────────────────────────────────────────────

def print_qr(url):
    try:
        qr = qrcode.QRCode(border=1)
        qr.add_data(url)
        qr.make(fit=True)
        print()
        qr.print_ascii(invert=True)
        print()
    except Exception:
        pass   # QR opzionale


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    token = ensure_authtoken()

    from pyngrok import ngrok, conf
    conf.get_default().auth_token = token

    # Avvia il tunnel PRIMA di Flask (Flask gira in thread)
    print("  Apertura tunnel ngrok...")
    try:
        tunnel = ngrok.connect(5000, "http")
        public_url = tunnel.public_url
        if public_url.startswith("http://"):
            public_url = public_url.replace("http://", "https://")
    except Exception as e:
        print(f"\n  ERRORE ngrok: {e}")
        print("  Controlla che il token sia corretto su dashboard.ngrok.com")
        sys.exit(1)

    print()
    print("=" * 60)
    print("  DASHBOARD ONLINE")
    print("=" * 60)
    print(f"  PC locale : http://localhost:5000")
    print(f"  Cellulare : {public_url}")
    print()
    print("  Inquadra il QR dal telefono:")
    print_qr(public_url)
    print("  Tieni questa finestra aperta.")
    print("  Premi Ctrl+C per fermare tutto.")
    print("=" * 60)
    print()

    # Apri browser locale
    def open_browser():
        import time; time.sleep(1)
        webbrowser.open("http://localhost:5000")
    threading.Thread(target=open_browser, daemon=True).start()

    # Avvia Flask (blocca qui fino a Ctrl+C)
    import dashboard
    dashboard.app.run(debug=False, port=5000)


if __name__ == "__main__":
    main()
