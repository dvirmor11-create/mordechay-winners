from flask import Flask, request, render_template_string, session, redirect, url_for
import sqlite3
import os
import random
import requests
from datetime import datetime, timedelta

app = Flask(__name__)
app.secret_key = "secret_key_for_app_123"
db_path = os.path.join(os.path.dirname(__file__), "database.db")

# מפתח ה-API האישי שלך
API_KEY = "e82bd0d32359350788242541846dc07a"

def get_db():
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS users (name TEXT PRIMARY KEY, balance INTEGER)")
        conn.execute("CREATE TABLE IF NOT EXISTS games (id INTEGER PRIMARY KEY, team1 TEXT, team2 TEXT, logo1 TEXT, logo2 TEXT, odd_1 REAL, odd_x REAL, odd_2 REAL, status TEXT DEFAULT 'open', result TEXT)")
        conn.execute("CREATE TABLE IF NOT EXISTS bets (id INTEGER PRIMARY KEY AUTOINCREMENT, user TEXT, game_id INTEGER, guess TEXT, amount INTEGER, timestamp TEXT, status TEXT DEFAULT 'pending')")
        conn.commit()
        
        count = conn.execute("SELECT COUNT(*) FROM games WHERE status = 'open'").fetchone()[0]
        if count == 0:
            generate_weekly_games(conn)

def generate_weekly_games(conn):
    conn.execute("DELETE FROM games WHERE status = 'open'")
    
    match_list = [
        ("מכבי תל אביב", "מכבי חיפה", "https://media.api-sports.io/football/teams/739.png", "https://media.api-sports.io/football/teams/743.png", 1.85, 3.25, 3.80),
        ("הפועל באר שבע", "בית\"ר ירושלים", "https://media.api-sports.io/football/teams/746.png", "https://media.api-sports.io/football/teams/740.png", 2.10, 3.10, 3.10),
        ("הפועל תל אביב", "מכבי נתניה", "https://media.api-sports.io/football/teams/741.png", "https://media.api-sports.io/football/teams/747.png", 2.20, 3.00, 2.95),
        ("הפועל חיפה", "בני סכנין", "https://media.api-sports.io/football/teams/742.png", "https://media.api-sports.io/football/teams/755.png", 2.05, 3.10, 3.20),
        ("בני יהודה", "הפועל פתח תקווה", "https://media.api-sports.io/football/teams/745.png", "https://media.api-sports.io/football/teams/748.png", 2.40, 3.00, 2.60)
    ]
    
    for idx, (t1, t2, l1, l2, o1, ox, o2) in enumerate(match_list, start=1):
        conn.execute("INSERT OR REPLACE INTO games (id, team1, team2, logo1, logo2, odd_1, odd_x, odd_2, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'open')",
                     (idx, t1, t2, l1, l2, o1, ox, o2))
    conn.commit()

def fetch_live_games():
    if not API_KEY or API_KEY == "YOUR_API_KEY_HERE":
        return False
    
    today = datetime.now().strftime("%Y-%m-%d")
    next_week = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
    
    # שאיבת משחקים מליגה לאומית (390) מ-היום ועד 7 ימים קדימה
    url = f"https://v3.football.api-sports.io/fixtures?league=390&season=2026&from={today}&to={next_week}"
    headers = {'x-rapidapi-host': "v3.football.api-sports.io", 'x-rapidapi-key': API_KEY}
    
    try:
        response = requests.get(url, headers=headers).json()
        fixtures = response.get('response', [])
        
        # אם אין משחקים בשבעת הימים הקרובים, משוך את 10 המשחקים הקרובים בליגה
        if not fixtures:
            url_next = "https://v3.football.api-sports.io/fixtures?league=390&season=2026&next=10"
            response = requests.get(url_next, headers=headers).json()
            fixtures = response.get('response', [])

        if not fixtures:
            return False

        with get_db() as conn:
            conn.execute("DELETE FROM games WHERE status = 'open'")
            for idx, game in enumerate(fixtures, start=1):
                t1 = game['teams']['home']['name']
                t2 = game['teams']['away']['name']
                l1 = game['teams']['home']['logo']
                l2 = game['teams']['away']['logo']
                o1, ox, o2 = round(random.uniform(1.8, 2.5), 2), round(random.uniform(2.8, 3.5), 2), round(random.uniform(2.0, 3.0), 2)
                conn.execute("INSERT INTO games (id, team1, team2, logo1, logo2, odd_1, odd_x, odd_2, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'open')",
                             (idx, t1, t2, l1, l2, o1, ox, o2))
            conn.commit()
        return True
    except Exception as e:
        print("Error fetching API:", e)
        return False

init_db()

HTML_TEMPLATE = """<!DOCTYPE html>
<html dir="rtl" lang="he">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ווינר חברים</title>
    <style>
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; text-align: center; background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%); color: #fff; margin: 0; padding: 10px; min-height: 100vh; }
        .container { max-width: 600px; margin: 0 auto; }
        .card { background: rgba(255, 255, 255, 0.95); color: #333; padding: 20px; margin: 15px auto; border-radius: 12px; box-shadow: 0 4px 10px rgba(0,0,0,0.3); }
        button { background: #ff4757; color: white; border: none; padding: 10px 20px; border-radius: 8px; cursor: pointer; font-weight: bold; width: 100%; margin-top: 10px; font-size: 16px; }
        button:hover { background: #ff6b81; }
        input[type="text"], input[type="number"] { padding: 10px; margin: 5px 0; border: 1px solid #ccc; border-radius: 8px; width: 90%; box-sizing: border-box; font-size: 16px; }
        .nav { display: flex; justify-content: space-around; background: rgba(0,0,0,0.5); padding: 10px; border-radius: 12px; margin-bottom: 20px; }
        .nav a { color: white; text-decoration: none; font-weight: bold; }
        .nav a:hover { color: #ff4757; }
        table { width: 100%; border-collapse: collapse; margin-top: 10px; color: #333; }
        th, td { padding: 10px; border-bottom: 1px solid #ddd; text-align: center; }
        .team-logo { width: 50px; height: 50px; object-fit: contain; }
