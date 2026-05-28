"""
Pubblica un mockup su surge.sh e restituisce l'URL.
Uso: python deploy_mockup.py nuova-immagine
"""
import sys
import os
import subprocess
from dotenv import load_dotenv

load_dotenv()

def deploy(client_slug: str):
    folder = os.path.join("clienti", client_slug)
    if not os.path.isdir(folder):
        print(f"Cartella non trovata: {folder}")
        sys.exit(1)

    domain = f"restyling-{client_slug}.surge.sh"
    token = os.getenv("SURGE_TOKEN", "")

    env = os.environ.copy()
    if token:
        env["SURGE_TOKEN"] = token

    print(f"Pubblicando {folder} su https://{domain} ...")
    result = subprocess.run(
        ["npx.cmd", "--yes", "surge", folder, domain],
        env=env, capture_output=False
    )

    if result.returncode == 0:
        print(f"\nMockup online: https://{domain}")
    else:
        print("\nErrore nel deploy. Controlla che surge sia autenticato.")
        print("Esegui una volta: npx surge login")

if __name__ == "__main__":
    slug = sys.argv[1] if len(sys.argv) > 1 else input("Nome cliente (es. nuova-immagine): ").strip()
    deploy(slug)
