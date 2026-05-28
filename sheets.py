import os
import gspread
from google.oauth2.service_account import Credentials
from dotenv import load_dotenv

load_dotenv()

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

COLUMNS = [
    "Attività", "Città", "Categoria", "Sito", "Telefono", "Email",
    "Tecnologia sito", "Ha prenotazioni?", "Tipo integrazione", "Score", "Note",
]

_worksheet_cache = None


def get_sheet():
    global _worksheet_cache
    if _worksheet_cache is not None:
        return _worksheet_cache

    creds_path = os.path.join(os.path.dirname(__file__), "credentials.json")
    creds = Credentials.from_service_account_file(creds_path, scopes=SCOPES)
    client = gspread.authorize(creds)

    sheet_id = os.getenv("GOOGLE_SHEET_ID", "").strip().rstrip("/")
    spreadsheet = client.open_by_key(sheet_id)
    _worksheet_cache = spreadsheet.sheet1
    return _worksheet_cache


def ensure_header(worksheet):
    existing = worksheet.row_values(1)
    if existing != COLUMNS:
        worksheet.insert_row(COLUMNS, 1)


def _build_row(prospect: dict) -> list:
    return [
        prospect.get("name", ""),
        prospect.get("city", ""),
        prospect.get("category", ""),
        prospect.get("website", ""),
        prospect.get("phone", ""),
        prospect.get("email", ""),
        prospect.get("technology", ""),
        "Sì" if prospect.get("has_bookings") else "No",
        ", ".join(prospect.get("integrations", [])),
        prospect.get("score", 0),
        prospect.get("note", ""),
    ]


def write_prospect(prospect: dict):
    ws = get_sheet()
    ensure_header(ws)
    ws.append_row(_build_row(prospect))


def write_prospects(prospects: list):
    if not prospects:
        return
    ws = get_sheet()
    ensure_header(ws)
    ws.append_rows([_build_row(p) for p in prospects])
    print(f"  -> {len(prospects)} prospect scritti sul foglio.")
