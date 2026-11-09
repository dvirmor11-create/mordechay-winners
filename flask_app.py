from flask import Flask, request, render_template_string, session, redirect
import sqlite3, os, requests, re
from datetime import datetime, timedelta, timezone

app = Flask(__name__)
app.secret_key = "winner_secret_key_123"
db_path = os.path.join(os.path.dirname(__file__), "database.db")
API_KEY = "e82bd0d32359350788242541846dc07a"

ALLOWED_LEAGUES = [383, 390, 140, 39, 5, 2, 3, 848]

TRANSLATIONS_MAP = {
    # ישראל
    "Maccabi Tel Aviv": "מכבי תל אביב", "Maccabi Haifa": "מכבי חיפה", "Hapoel Beer Sheva": "הפועל באר שבע",
    "Beitar Jerusalem": "בית\"ר ירושלים", "Hapoel Tel Aviv": "הפועל תל אביב", "Maccabi Netanya": "מכבי נתניה",
    "Hapoel Haifa": "הפועל חיפה", "Bnei Sakhnin": "בני סכנין", "Hapoel Jerusalem": "הפועל ירושלים",
    "Maccabi Bnei Raina": "מכבי בני ריינה", "Hapoel Hadera": "הפועל חדרה", "Ironi Kiryat Shmona": "עירוני ק\"ש",
    "Maccabi Petah Tikva": "מכבי פ\"ת", "F.C. Ashdod": "מ.ס. אשדוד", "Hapoel Petah Tikva": "הפועל פ\"ת",
    "Bnei Yehuda": "בני יהודה", "Hapoel Kfar Saba": "הפועל כפ\"ס", "Hapoel Ramat Gan": "הפועל ר\"ג",
    "Hapoel Rishon LeZion": "הפועל ראשל\"צ", "Hapoel Afula": "הפועל עפולה", "Hapoel Umm al-Fahm": "אום אל-פחם",
    "Maccabi Jaffa": "מכבי יפו", "Hapoel Nir Ramat HaSharon": "רמת השרון", "Ironi Tiberias": "עירוני טבריה",
    "Maccabi Herzliya": "מכבי הרצליה", "Sektzia Nes Tziona": "נס ציונה", "Hapoel Nof HaGalil": "נוף הגליל",
    # עולם
    "Real Madrid": "ריאל מדריד", "Barcelona": "ברצלונה", "Atletico Madrid": "אתלטיקו מדריד",
    "Arsenal": "ארסנל", "Manchester City": "מנצ'סטר סיטי", "Liverpool": "ליברפול", "Chelsea": "צ'לסי",
    "Tottenham": "טוטנהאם", "Manchester United": "מנצ'סטר יונייטד",
    "Israel": "ישראל", "France": "צרפת", "Italy": "איטליה", "Spain": "ספרד", "England": "אנגליה"
}

def translate_team(name):
    if name in TRANSLATIONS_MAP: return TRANSLATIONS_MAP[name]
    clean = re.sub(r'\b(FC|F\.C\.|Club|Town|City|United)\b', '', name, flags=re.IGNORECASE).strip()
    return TRANSLATIONS_MAP.get(clean, clean)

def get_db():
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS users (name TEXT PRIMARY KEY, balance INTEGER)")
        conn.execute("CREATE TABLE IF NOT EXISTS games (id INTEGER PRIMARY KEY, fixture_id INTEGER, team1 TEXT, team2 TEXT, logo1 TEXT, logo2 TEXT, odd_1 REAL, odd_x REAL, odd_2 REAL
