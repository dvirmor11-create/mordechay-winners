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
        conn.execute("CREATE TABLE IF NOT EXISTS games (id INTEGER PRIMARY KEY, fixture_id INTEGER, team1 TEXT, team2 TEXT, logo1 TEXT, logo2 TEXT, odd_1 REAL, odd_x REAL, odd_2 REAL, status TEXT DEFAULT 'open', match_time TEXT, timestamp REAL)")
        conn.execute("CREATE TABLE IF NOT EXISTS bets (id INTEGER PRIMARY KEY AUTOINCREMENT, user TEXT, game_id INTEGER, guess TEXT, amount INTEGER, timestamp TEXT, status TEXT DEFAULT 'pending')")
        conn.commit()

init_db()

# ================= משיכת נתונים (חיסכון ב-API) =================

def fetch_games_and_odds():
    headers = {'x-apisports-key': API_KEY}
    today = datetime.now().strftime("%Y-%m-%d")
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    
    fixtures = []
    # משיכת משחקים פתוחים בלבד (NS) להיום ומחר
    for date in [today, tomorrow]:
        res = requests.get(f"https://v3.football.api-sports.io/fixtures?date={date}&status=NS", headers=headers, timeout=8).json()
        if res.get('response'): fixtures.extend(res['response'])
        
    filtered = [g for g in fixtures if g.get('league', {}).get('id') in ALLOWED_LEAGUES][:10]
    if not filtered: return False, "לא נמצאו משחקים רלוונטיים"

    with get_db() as conn:
        conn.execute("DELETE FROM games WHERE status = 'open'")
        for idx, g in enumerate(filtered, start=1):
            f_id = g['fixture']['id']
            t1, t2 = translate_team(g['teams']['home']['name']), translate_team(g['teams']['away']['name'])
            l1, l2 = g['teams']['home']['logo'], g['teams']['away']['logo']
            ts = g['fixture']['timestamp']
            
            try:
                dt = datetime.fromtimestamp(ts, tz=timezone(timedelta(hours=2)))
                m_time = dt.strftime("%d/%m %H:%M")
            except:
                m_time = ""

            # משיכת יחסים
            o1, ox, o2 = 9.99, 9.99, 9.99
            try:
                odds_res = requests.get(f"https://v3.football.api-sports.io/odds?fixture={f_id}&bet=1", headers=headers, timeout=6).json()
                if odds_res.get('response') and odds_res['response'][0].get('bookmakers'):
                    bm = odds_res['response'][0]['bookmakers'][0]
                    for bet in bm.get('bets', []):
                        if bet.get('id') == 1:
                            val = {str(v['value']): float(v['odd']) for v in bet['values']}
                            o1, ox, o2 = val.get('Home', 9.99), val.get('Draw', 9.99), val.get('Away', 9.99)
            except: pass

            conn.execute("INSERT INTO games (id, fixture_id, team1, team2, logo1, logo2, odd_1, odd_x, odd_2, status, match_time, timestamp) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'open', ?, ?)", 
                         (idx, f_id, t1, t2, l1, l2, o1, ox, o2, m_time, ts))
        conn.commit()
    return True, "המשחקים ויחסי ההימורים עודכנו בהצלחה."

def check_results_and_payout():
    headers = {'x-apisports-key': API_KEY}
    with get_db() as conn:
        games = conn.execute("SELECT id, fixture_id, odd_1, odd_x, odd_2 FROM games WHERE status = 'open'").fetchall()
        for g in games:
            try:
                res = requests.get(f"https://v3.football.api-sports.io/fixtures?id={g['fixture_id']}", headers=headers, timeout=5).json()
                if not res.get('response'): continue
                match = res['response'][0]
                status = match['fixture']['status']['short']
                
                # אם המשחק הסתיים (FT, AET, PEN)
                if status in ['FT', 'AET', 'PEN']:
                    home = match['goals']['home']
                    away = match['goals']['away']
                    result = '1' if home > away else ('2' if away > home else 'X')
                    
                    conn.execute("UPDATE games SET status = 'closed' WHERE id = ?", (g['id'],))
                    bets = conn.execute("SELECT id, user, amount, guess FROM bets WHERE game_id = ? AND status = 'pending'", (g['id'],)).fetchall()
                    
                    for b in bets:
                        if b['guess'] == result:
                            odd = g['odd_1'] if result == '1' else (g['odd_x'] if result == 'X' else g['odd_2'])
                            win_amount = int(b['amount'] * odd)
                            conn.execute("UPDATE users SET balance = balance + ? WHERE name = ?", (win_amount, b['user']))
                            conn.execute("UPDATE bets SET status = 'won' WHERE id = ?", (b['id'],))
                        else:
                            conn.execute("UPDATE bets SET status = 'lost' WHERE id = ?", (b['id'],))
            except: pass
        conn.commit()
    return "בדיקת תוצאות וחלוקת כספים הסתיימה."

# ================= מסלולים וקוד חזותי =================

HTML = """<!DOCTYPE html>
<html dir="rtl" lang="he">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Winner חברים</title>
<style>
body { font-family: system-ui, sans-serif; background: #f4f4f4; color: #333; margin: 0; padding-bottom: 20px; }
.header { background: #002c5f; color: #fff; text-align: center; padding: 15px; }
.header h1 { margin: 0; font-size: 24px; color: #ffeb3b; }
.nav { background: #004085; display: flex; justify-content: center; padding: 10px; flex-wrap: wrap; }
.nav a { color: #fff; text-decoration: none; padding: 8px 15px; margin: 5px; background: rgba(255,255,255,0
