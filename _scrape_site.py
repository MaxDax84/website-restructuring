import requests
from bs4 import BeautifulSoup

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0"}
URL = "https://nuova-immagine-coiffeur.durable.site/"

resp = requests.get(URL, headers=HEADERS, timeout=15)
soup = BeautifulSoup(resp.text, "html.parser")

# Remove script/style noise
for tag in soup(["script", "style", "noscript", "svg", "img"]):
    tag.decompose()

text = soup.get_text(separator="\n", strip=True)
with open("_site_content.txt", "w", encoding="utf-8") as f:
    f.write(text)
print("Salvato in _site_content.txt")
