from flask import Flask, request, render_template_string, session, redirect, url_for
import sqlite3, os, requests
from datetime import datetime, timedelta, timezone

app = Flask(__name__)
app.secret_key = "secret_key_123"
db_path = os.path.join(os.path.dirname(__file__), "database.db")
API_KEY = "e82bd0d32359350788242541846dc07a"

PREFERRED_LEAGUES = [5, 383, 390, 2, 39, 140, 135, 78, 61]

def get_db():
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS users (name TEXT PRIMARY KEY, balance INTEGER)")
        conn.execute("CREATE TABLE IF NOT EXISTS games (id INTEGER PRIMARY KEY, team1 TEXT, team2 TEXT, logo1 TEXT, logo2 TEXT, odd_1 REAL, odd_x REAL, odd_2 REAL, status TEXT DEFAULT 'open', result TEXT, match_time TEXT)")
        conn.execute("CREATE TABLE IF NOT EXISTS bets (id INTEGER PRIMARY KEY AUTOINCREMENT, user TEXT, game_id INTEGER, guess TEXT, amount INTEGER, timestamp TEXT, status TEXT DEFAULT 'pending')")
        conn.commit()

def get_real_odds(fixture_id, headers):
    url = f"https://v3.football.api-sports.io/odds?fixture={fixture_id}&bet=1"
    try:
        res = requests.get(url, headers=headers, timeout=6).json()
        resp = res.get('response', [])
        if resp and resp[0].get('bookmakers'):
            bookmakers = resp[0]['bookmakers']
            selected_bm = None
            for preferred_id in [8, 1, 2, 6]:
                for bm in bookmakers:
                    if bm.get('id') == preferred_id:
                        selected_bm = bm
                        break
                if selected_bm: break
            
            if not selected_bm:
                selected_bm = bookmakers[0]

            for bet in selected_bm.get('bets', []):
                if bet.get('id') == 1 or bet.get('name') == 'Match Winner':
                    val_map = {str(v.get('value')): float(v.get('odd')) for v in bet.get('values', [])}
                    o1 = val_map.get('Home') or val_map.get('1')
                    ox = val_map.get('Draw') or val_map.get('X')
                    o2 = val_map.get('Away') or val_map.get('2')
                    if o1 and ox and o2:
                        return round(o1, 2), round(ox, 2), round(o2, 2)
    except Exception as e:
        print(f"Error fetching odds for fixture {fixture_id}:", e)
    return None, None, None

def fetch_live_games():
    if not API_KEY: return False, "חסר מפתח API"
    headers = {'x-apisports-key': API_KEY, 'x-rapidapi-key': API_KEY, 'x-rapidapi-host': "v3.football.api-sports.io"}
    
    raw_fixtures = []
    for day_offset in range(0, 5):
        target_date = (datetime.now() + timedelta(days=day_offset)).strftime("%Y-%m-%d")
        url = f"https://v3.football.api-sports.io/fixtures?date={target_date}&status=NS"
        try:
            res = requests.get(url, headers=headers, timeout=5).json()
            if res.get('response'):
                raw_fixtures.extend(res['response'])
        except Exception as e:
            print(e)

    if not raw_fixtures:
        return False, "לא נמצאו משחקים עתידיים בימים הקרובים"

    top_fixtures = [g for g in raw_fixtures if g.get('league', {}).get('id') in PREFERRED_LEAGUES]
    other_fixtures = [g for g in raw_fixtures if g.get('league', {}).get('id') not in PREFERRED_LEAGUES]
    
    top_fixtures.sort(key=lambda g: PREFERRED_LEAGUES.index(g['league']['id']))
    final_fixtures = (top_fixtures + other_fixtures)[:10]

    with get_db() as conn:
        conn.execute("DELETE FROM games WHERE status = 'open'")
        for idx, g in enumerate(final_fixtures, start=1):
            f_id = g['fixture']['id']
            t1, t2 = g['teams']['home']['name'], g['teams']['away']['name']
            l1, l2 = g['teams']['home']['logo'], g['teams']['away']['logo']
            
            raw_date = g['fixture'].get('date', '')
            try:
                dt = datetime.fromisoformat(raw_date.replace('Z', '+00:00')).astimezone(timezone(timedelta(hours=2)))
                m_time = dt.strftime("%d/%m ב-%H:%M")
            except:
                m_time = ""

            o1, ox, o2 = get_real_odds(f_id, headers)
            # אם אין יחס אמיתי בסוכנויות, יוצר ברירת מחדל בולטת וברורה (9.99)
            if not o1:
                o1, ox, o2 = 9.99, 9.99, 9.99

            conn.execute("INSERT INTO games (id, team1, team2, logo1, logo2, odd_1, odd_x, odd_2, status, match_time) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'open', ?)", 
                         (idx, t1, t2, l1, l2, o1, ox, o2, m_time))
        conn.commit()
    return True, f"נטענו {len(final_fixtures)} משחקים בהצלחה!"

init_db()

HTML = """<!DOCTYPE html>
<html dir="rtl" lang="he">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ווינר חברים ⚽</title>
<style>
body { font-family: system-ui, -apple-system, sans-serif; text-align: center; background: #1e3c72; color: #fff; padding: 10px; margin: 0; }
.card { background: #fff; color: #333; padding: 15px; margin: 12px auto; max-width: 480px; border-radius: 10px; box-shadow: 0 4px 8px rgba(0,0,0,0.2); }
button { background: #ff4757; color: white; border: none; padding: 10px 15px; border-radius: 6px; cursor: pointer; font-weight: bold; width: 100%; margin-top: 8px; font-size: 15px; }
button:hover { background: #e03847; }
input { padding: 8px; margin: 5px; border: 1px solid #ccc; border-radius: 5px; text-align: center; }
.nav { margin-bottom: 15px; }
.nav a { color: #fff; margin: 0 4px; font-weight: bold; text-decoration: none; background: rgba(255,255,255,0.15); padding: 6px 10px; border-radius: 20px; font-size: 13px; display: inline-block; margin-top:4px; }
.match-header { display: flex; align-items: center; justify-content: space-between; direction: ltr; margin: 10px 0; }
.team-side { display: flex; align-items: center; gap: 6px; flex: 1; }
.team-side.home { justify-content: flex-start; text-align: left; }
.team-side.away { justify-content: flex-end; text-align: right; }
.team-logo { width: 36px; height: 36px; object-fit: contain; }
.vs-badge { font-weight: bold; color: #ff4757; padding: 0 8px; font-size: 14px; }
.time-tag { font-size: 0.8
