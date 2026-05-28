"""
Utility: deduplica il foglio e arricchisce le email mancanti.
"""
from sheets import get_sheet, COLUMNS
from analyzer import extract_email, fetch_html

ws = get_sheet()
rows = ws.get_all_values()

if not rows:
    print("Foglio vuoto.")
    exit()

header = rows[0]
data = rows[1:]

# --- Step 1: Deduplica per URL ---
seen_urls = set()
unique = []
for row in data:
    url = row[3].strip().rstrip("/") if len(row) > 3 else ""
    if url not in seen_urls:
        seen_urls.add(url)
        unique.append(row)

removed = len(data) - len(unique)
if removed:
    print(f"Rimossi {removed} doppioni.")

# --- Step 2: Arricchisci email mancanti ---
EMAIL_COL = 5  # indice della colonna Email (0-based)

for i, row in enumerate(unique):
    # Estendi la riga se ha meno colonne dell'header
    while len(row) < len(COLUMNS):
        row.append("")

    current_email = row[EMAIL_COL].strip()
    url = row[3].strip()

    if current_email:
        print(f"[{i+1}] {row[0][:40]} — email gia presente: {current_email}")
        continue

    print(f"[{i+1}] {row[0][:40]} — cerco email su {url} ...")
    html, final_url = fetch_html(url)
    if html:
        email = extract_email(html, final_url)
        if email:
            row[EMAIL_COL] = email
            print(f"       trovata: {email}")
        else:
            print("       non trovata")
    else:
        print(f"       sito non raggiungibile")

# --- Step 3: Riscrivi il foglio ---
ws.clear()
ws.append_row(COLUMNS)
if unique:
    ws.append_rows(unique)

print(f"\nFoglio aggiornato: {len(unique)} righe.")
