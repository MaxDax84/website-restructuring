# Website Restructuring — Note di progetto

## Obiettivo
Pipeline automatica per trovare attività locali con siti datati, generare mockup di restyling professionali e presentarli ai potenziali clienti.

---

## Flusso completo

1. **Scout** (`scout.py`): cerca attività su Google Places API, analizza il loro sito con `analyzer.py`, scrive i prospect qualificati su Google Sheets (`sheets.py`)
2. **Dashboard** (`dashboard.py`): interfaccia web locale (Flask porta 5000) per gestire i mockup
3. **Generazione** (`generator.py`): pipeline scraping → immagini → Claude API → HTML
4. **Deploy** (`deploy_mockup.py`): pubblica su surge.sh

---

## Avvio

| File | Cosa fa |
|---|---|
| `Avvia Dashboard.bat` | Dashboard solo locale (http://localhost:5000) |
| `Avvia Dashboard Online.bat` | Dashboard + tunnel ngrok (accesso da cellulare) — richiede NGROK_AUTHTOKEN nel .env |

---

## Struttura cartelle

```
Website Restructuring/
  clienti/                    ← un sottocartella per ogni cliente
    <slug>/
      index.html              ← mockup generato
      robots.txt              ← noindex (evita Google)
      img/
        img-01.webp ... img-09.webp
  templates/
    mockup_base.html          ← template Jinja2 di fallback (usato se API non disponibile)
  mockups_registry.json       ← registro tutti i siti
```

---

## Dashboard — funzionalità card

Ogni card mostra: nome, dominio surge, stato, costo generazione (se generato con Claude).

| Pulsante | Azione |
|---|---|
| **Apri** | Apre il sito su surge (solo se Live/Protetto) |
| **Anteprima locale** | Mostra il mockup in locale via Flask |
| **Attiva** | Deploy su surge.sh |
| **Disattiva** | Teardown da surge (sito offline) |
| **Aggiungi password** | Inietta JS gate con password SHA-256 e rideploya |
| **Rimuovi password** | Rimuove il gate e rideploya |
| **Elimina** | Rimuove da surge + cancella cartella locale + registry (richiede conferma popup) |

Quando una generazione è in corso la card mostra barra di progresso e testo di stato aggiornato in tempo reale (polling ogni 1.5s).

---

## Generazione mockup — regole FONDAMENTALI

### Cosa deve fare Claude
- Analizzare il sito originale e capirne stile, brand, colori, identità
- Riprodurre TUTTI i contenuti del sito originale (ogni sezione, ogni servizio, ogni testo)
- Creare un HTML moderno che sia il "nuovo sito" di quella attività — non una versione semplificata
- Usare il CSS base del template (fornito nel prompt) e aggiungere solo gli override del brand
- Immagini scaricate disponibili in `img/img-01.webp` ... `img-09.webp`

### Cosa NON deve fare Claude
- NON troncare i contenuti
- NON semplificare le sezioni
- NON omettere servizi, prezzi, testi presenti nell'originale
- NON usare placeholder generici se il contenuto reale è disponibile

### Qualità attesa
- Smooth scroll su tutti i link interni (`html { scroll-behavior: smooth; }`)
- Popup telefono al click su "Prenota/Chiama" (JavaScript vanilla)
- Responsive mobile-first
- Tutte le sezioni del sito originale presenti
- Schema.org JSON-LD per il tipo di attività
- `<meta name="robots" content="noindex,nofollow">` sempre presente

### Costi indicativi (Claude Sonnet 4.6)
- Input: $3.00/1M token
- Output: $15.00/1M token
- Per mockup tipico: ~$0.09–0.15

---

## API Keys (.env)

| Variabile | Servizio |
|---|---|
| `PLACES_API_KEY` | Google Places (scout) |
| `GOOGLE_SHEET_ID` | Google Sheets (prospect) |
| `SURGE_TOKEN` | surge.sh (deploy) |
| `ANTHROPIC_API_KEY` | Claude API (generazione mockup) |
| `NGROK_AUTHTOKEN` | ngrok (accesso mobile) — aggiunto al primo avvio online |

---

## Architettura generazione — due chiamate separate

Claude Sonnet 4.6 ha max 8192 token per chiamata. Un sito completo richiede ~15.000+ token.
**Soluzione**: pipeline a due chiamate + loop di continuazione.

| Chiamata | Contenuto | Max token |
|---|---|---|
| Call 1 — CSS | Solo CSS del brand (variabili colore, layout, responsive) | 3000 |
| Call 2 — HTML | Intero body HTML con tutti i contenuti reali | 8192 |
| Continuation loop | Se `</html>` manca, continua fino a 3 volte | 4096/volta |

Ogni mockup è completamente indipendente — zero riuso CSS da altri clienti.
CSS ispirato ai colori estratti dal sito originale del cliente.

---

## Surge — gestione siti

- Ogni mockup ha dominio `restyling-<slug>.surge.sh`
- `robots.txt` con `Disallow: /` impedisce l'indicizzazione su Google
- Teardown con `npx.cmd surge teardown <dominio>`
- Account: massimo.dassano@gmail.com

---

## Primo cliente di esempio

- Slug: `nuova-immagine`
- Nome: Nuova Immagine Coiffeur (parrucchiere, Milano)
- Sito originale: https://nuova-immagine-coiffeur.durable.site/
- Mockup: https://restyling-nuova-immagine.surge.sh
- Questo mockup è stato costruito MANUALMENTE (non con Claude) — è il template di riferimento visivo
