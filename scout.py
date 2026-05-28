import os
import sys
import time
import requests
from dotenv import load_dotenv
from analyzer import analyze
from sheets import write_prospects

load_dotenv()

PLACES_API_KEY = os.getenv("PLACES_API_KEY")
PLACES_TEXT_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"

# Fields we need from the new Places API
FIELD_MASK = "places.id,places.displayName,places.websiteUri,places.nationalPhoneNumber"


def search_places(query: str, page_token: str = None) -> dict:
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": PLACES_API_KEY,
        "X-Goog-FieldMask": FIELD_MASK,
    }
    body = {"textQuery": query, "languageCode": "it", "maxResultCount": 20}
    if page_token:
        body["pageToken"] = page_token

    resp = requests.post(PLACES_TEXT_SEARCH_URL, json=body, headers=headers, timeout=15)
    resp.raise_for_status()
    return resp.json()


def collect_places(category: str, city: str, max_results: int = 60) -> list:
    query = f"{category} {city}"
    print(f"Ricerca: '{query}'...")

    data = search_places(query)
    places = list(data.get("places", []))
    print(f"  {len(places)} trovati...")

    while len(places) < max_results:
        next_token = data.get("nextPageToken")
        if not next_token:
            break
        time.sleep(2)
        data = search_places(query, page_token=next_token)
        new = data.get("places", [])
        if not new:
            break
        places.extend(new)
        print(f"  {len(places)} trovati...")

    return places[:max_results]


def run_scout(category: str, city: str, min_score: int = 2):
    places = collect_places(category, city)
    print(f"\nAnalisi di {len(places)} attività...\n")

    prospects = []
    discarded = 0

    for i, place in enumerate(places, 1):
        # New API: displayName is an object {"text": "...", "languageCode": "it"}
        name = place.get("displayName", {}).get("text", "")
        website = place.get("websiteUri", "")
        phone = place.get("nationalPhoneNumber", "")

        print(f"[{i}/{len(places)}] {name}")

        if not website:
            print("  -> SCARTATO: nessun sito web")
            discarded += 1
            continue

        print(f"  Sito: {website}")

        try:
            analysis = analyze(website)
        except Exception as e:
            print(f"  -> ERRORE analisi: {e}")
            discarded += 1
            continue

        if analysis.get("discard"):
            print(f"  -> SCARTATO: {analysis.get('discard_reason', '')}")
            discarded += 1
            continue

        score = analysis.get("score", 0)
        if score < min_score:
            print(f"  -> SCARTATO: score troppo basso ({score}/10)")
            discarded += 1
            continue

        prospect = {
            "name": name,
            "city": city,
            "category": category,
            "website": website,
            "phone": phone,
            "email": analysis.get("email", ""),
            "technology": analysis.get("technology", ""),
            "has_bookings": analysis.get("has_bookings", False),
            "integrations": analysis.get("integrations", []),
            "score": score,
            "note": analysis.get("note", ""),
        }

        prospects.append(prospect)
        tech = prospect["technology"]
        note = prospect["note"]
        print(f"  -> QUALIFICATO  Score: {score}/10 | Tech: {tech} | {note}")

    print(f"\n{'=' * 50}")
    print(f"Risultati: {len(prospects)} qualificati, {discarded} scartati")

    if prospects:
        print("Scrivo su Google Sheets...")
        write_prospects(prospects)
    else:
        print("Nessun prospect da scrivere.")

    return prospects


if __name__ == "__main__":
    if len(sys.argv) >= 3:
        cat = sys.argv[1]
        cit = sys.argv[2]
        score_min = int(sys.argv[3]) if len(sys.argv) == 4 else 2
        run_scout(cat, cit, min_score=score_min)
    else:
        cat = input("Categoria (es. parrucchiere): ").strip()
        cit = input("Città (es. Milano): ").strip()
        run_scout(cat, cit)
