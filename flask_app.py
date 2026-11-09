from flask import Flask, request, render_template_string, session, redirect, url_for
import sqlite3
import os
import random
import requests
from datetime import datetime

app = Flask(__name__)
app.secret_key = "secret_key_for_app_123"
db_path = os.path.join(os.path.dirname(__file__), "database.db")

# שים כאן את מפתח ה-API החינמי שלך מ- api-football.com כדי לשאוב נתונים בלייב
API_KEY = "YOUR_API_KEY_HERE"

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
    
    # רשימת גיבוי במקרה שאין עדיין מפתח API פעיל
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
    if API_KEY == "YOUR_API_KEY_HERE":
        return False # מדלג אם אין מפתח וממשיך להשתמש ברשימת הגיבוי
    
    url = "https://v3.football.api-sports.io/fixtures?league=390&season=2024&next=5" # 390 = ליגה לאומית / ליגת העל
    headers = {'x-rapidapi-host': "v3.football.api-sports.io", 'x-rapidapi-key': API_KEY}
    
    try:
        response = requests.get(url, headers=headers).json()
        with get_db() as conn:
            conn.execute("DELETE FROM games WHERE status = 'open'")
            for idx, game in enumerate(response['response'], start=1):
                t1 = game['teams']['home']['name']
                t2 = game['teams']['away']['name']
                l1 = game['teams']['home']['logo']
                l2 = game['teams']['away']['logo']
                # יחסים מדומים או משיכת יחסים מנקודת Odds ב-API (דורש קריאה נוספת)
                o1, ox, o2 = round(random.uniform(1.8, 2.5), 2), round(random.uniform(2.8, 3.5), 2), round(random.uniform(2.0, 3.0), 2)
                conn.execute("INSERT INTO games (id, team1, team2, logo1, logo2, odd_1, odd_x, odd_2, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'open')",
                             (idx, t1, t2, l1, l2, o1, ox, o2))
            conn.commit()
        return True
    except Exception as e:
        print("Error fetching API:", e)
        return False

init_db()

HTML_TEMPLATE = """
<!DOCTYPE html>
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
        .match-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px; font-weight: bold; }
        .match-header div { flex: 1; }
        .odds-selector { display: flex; justify-content: space-between; margin-bottom: 10px; }
        .odds-selector input[type="radio"] { display: none; }
        .odds-selector label { flex: 1; margin: 0 5px; padding: 10px; background: #e0e0e0; border-radius: 8px; cursor: pointer; font-weight: bold; border: 2px solid transparent; transition: 0.2s; color: #333; }
        .odds-selector input[type="radio"]:checked + label { background: #ff4757; color: white; border-color: #ff4757; }
        .status-won { color: green; font-weight: bold; }
        .status-lost { color: red; font-weight: bold; }
        .status-pending { color: orange; font-weight: bold; }
        .alert { background-color: #ff4757; color: white; padding: 10px; border-radius: 8px; margin-bottom: 15px; font-weight: bold; }
    </style>
</head>
<body>
    <div class="container">
        <h1>ווינר חברים ⚽</h1>
        
        {% if error_msg %}
            <div class="alert">{{ error_msg }}</div>
        {% endif %}
        
        {% if not user %}
            <div class="card">
                <h2>התחברות</h2>
                <form method="POST" action="/login">
                    <input type="text" name="username" placeholder="הכנס את השם שלך" required>
                    <button type="submit">היכנס למשחק</button>
                </form>
            </div>
        {% else %}
            <div class="nav">
                <a href="/">משחקים</a>
                <a href="/league">טבלת ליגה</a>
                <a href="/history">היסטוריית הימורים</a>
                <a href="/logout" style="color: #ff4757;">התנתק</a>
            </div>
            
            <h3>שלום {{ user }} | יתרה: {{ balance }} ₪</h3>
            
            {% if view == 'games' %}
                {% if not games %}
                    <div class="card"><p>אין כרגע משחקים פתוחים.</p></div>
                {% endif %}
                {% for g in games %}
                    <div class="card">
                        <div class="match-header">
                            <div><img src="{{ g['logo1'] }}" class="team-logo"><br>{{ g['team1'] }}</div>
                            <div>VS</div>
                            <div><img src="{{ g['logo2'] }}" class="team-logo"><br>{{ g['team2'] }}</div>
                        </div>
                        <form method="POST" action="/bet">
                            <input type="hidden" name="game_id" value="{{ g['id'] }}">
                            <div class="odds-selector">
                                <input type="radio" id="g{{g['id']}}_1" name="guess" value="1" required>
                                <label for="g{{g['id']}}_1">1<br>{{ g['odd_1'] }}</label>
                                
                                <input type="radio" id="g{{g['id']}}_x" name="guess" value="X">
                                <label for="g{{g['id']}}_x">X<br>{{ g['odd_x'] }}</label>
                                
                                <input type="radio" id="g{{g['id']}}_2" name="guess" value="2">
                                <label for="g{{g['id']}}_2">2<br>{{ g['odd_2'] }}</label>
                            </div>
                            <input type="number" name="amount" placeholder="סכום (₪)" min="1" max="{{ balance }}" required>
                            <button type="submit">שלח הימור</button>
                        </form>
                    </div>
                {% endfor %}
            
            {% elif view == 'league' %}
                <div class="card">
                    <h2>טבלת הליגה 🏆</h2>
                    <table>
                        <tr><th>מיקום</th><th>שם</th><th>יתרה (₪)</th></tr>
                        {% for u in users_league %}
                            <tr><td>{{ loop.index }}</td><td>{{ u['name'] }}</td><td>{{ u['balance'] }}</td></tr>
                        {% endfor %}
                    </table>
                </div>
                
            {% elif view == 'history' %}
                <div class="card">
                    <h2>ההימורים שלי 📜</h2>
                    <table>
                        <tr><th>משחק</th><th>הימור</th><th>סכום</th><th>סטטוס</th></tr>
                        {% for b in user_bets %}
                            <tr>
                                <td style="font-size: 0.9em;">{{ b['team1'] }} - {{ b['team2'] }}</td>
                                <td>{{ b['guess'] }}</td>
                                <td>{{ b['amount'] }}</td>
                                <td class="status-{{ b['status'] }}">
                                    {% if b['status'] == 'won' %}זכייה!{% elif b['status'] == 'lost' %}הפסד{% else %}ממתין{% endif %}
                                </td>
                            </tr>
                        {% endfor %}
                    </table>
                </div>
            {% endif %}
            
        {% endif %}
    </div>
</body>
</html>
"""

@app.route("/")
def index():
    user = session.get("user")
    error = request.args.get("error")
    error_msg = "כבר הימרת על המשחק הזה! לא ניתן להמר פעמיים." if error == "already_bet" else None
    
    if not user: return render_template_string(HTML_TEMPLATE, user=None)
    
    with get_db() as conn:
        user_row = conn.execute("SELECT balance FROM users WHERE name = ?", (user,)).fetchone()
        if not user_row:
            session.clear()
            return redirect(url_for("index"))
        balance = user_row["balance"]
        games = conn.execute("SELECT * FROM games WHERE status = 'open'").fetchall()
    return render_template_string(HTML_TEMPLATE, user=user, balance=balance, games=games, view='games', error_msg=error_msg)

@app.route("/league")
def league():
    user = session.get("user")
    if not user: return redirect(url_for("index"))
    
    with get_db() as conn:
        balance = conn.execute("SELECT balance FROM users WHERE name = ?", (user,)).fetchone()["balance"]
        users_league = conn.execute("SELECT name, balance FROM users ORDER BY balance DESC").fetchall()
    return render_template_string(HTML_TEMPLATE, user=user, balance=balance, users_league=users_league, view='league')

@app.route("/history")
def history():
    user = session.get("user")
    if not user: return redirect(url_for("index"))
    
    with get_db() as conn:
        balance = conn.execute("SELECT balance FROM users WHERE name = ?", (user,)).fetchone()["balance"]
        query = """SELECT b.guess, b.amount, b.status, g.team1, g.team2 
                   FROM bets b JOIN games g ON b.game_id = g.id 
                   WHERE b.user = ? ORDER BY b.id DESC"""
        user_bets = conn.execute(query, (user,)).fetchall()
    return render_template_string(HTML_TEMPLATE, user=user, balance=balance, user_bets=user_bets, view='history')

@app.route("/login", methods=["POST"])
def login():
    user = request.form.get("username", "").strip()
    if not user: return redirect(url_for("index"))
    session["user"] = user
    with get_db() as conn:
        if not conn.execute("SELECT name FROM users WHERE name = ?", (user,)).fetchone():
            conn.execute("INSERT INTO users (name, balance) VALUES (?, ?)", (user, 1000))
            conn.commit()
    return redirect(url_for("index"))

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))

@app.route("/bet", methods=["POST"])
def bet():
    user = session.get("user")
    amount = int(request.form.get("amount", 0))
    game_id = int(request.form.get("game_id"))
    guess = request.form.get("guess")
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    
    if user and amount > 0:
        with get_db() as conn:
            # תיקון הבאג: בדיקה אם המשתמש כבר הימר על המשחק הזה
            existing_bet = conn.execute("SELECT id FROM bets WHERE user = ? AND game_id = ?", (user, game_id)).fetchone()
            if existing_bet:
                return redirect(url_for("index", error="already_bet"))
            
            game = conn.execute("SELECT status FROM games WHERE id = ?", (game_id,)).fetchone()
            if game and game["status"] == 'open':
                row = conn.execute("SELECT balance FROM users WHERE name = ?", (user,)).fetchone()
                if row and row["balance"] >= amount:
                    conn.execute("UPDATE users SET balance = balance - ? WHERE name = ?", (amount, user))
                    conn.execute("INSERT INTO bets (user, game_id, guess, amount, timestamp, status) VALUES (?, ?, ?, ?, ?, 'pending')", 
                                 (user, game_id, guess, amount, timestamp))
                    conn.commit()
    return redirect(url_for("history"))

@app.route("/update_live")
def update_live():
    # כתובת לעדכון אוטומטי של המשחקים
    success = fetch_live_games()
    if not success:
        with get_db() as conn:
            generate_weekly_games(conn)
    return "Games updated", 200

@app.route("/check_results")
def check_results():
    with get_db() as conn:
        open_games = conn.execute("SELECT id FROM games WHERE status = 'open'").fetchall()
        for g in open_games:
            g_id = g['id']
            result = random.choice(['1', 'X', '2'])
            conn.execute("UPDATE games SET status = 'closed', result = ? WHERE id = ?", (result, g_id))
            
            pending_bets = conn.execute("SELECT id, user, amount, guess FROM bets WHERE game_id = ? AND status = 'pending'", (g_id,)).fetchall()
            for b in pending_bets:
                if str(b['guess']) == result:
                    odds = conn.execute("SELECT odd_1, odd_x, odd_2 FROM games WHERE id = ?", (g_id,)).fetchone()
                    odd = odds['odd_1'] if result == '1' else (odds['odd_x'] if result == 'X' else odds['odd_2'])
                    win_amount = int(b['amount'] * odd)
                    conn.execute("UPDATE users SET balance = balance + ? WHERE name = ?", (win_amount, b['user']))
                    conn.execute("UPDATE bets SET status = 'won' WHERE id = ?", (b['id'],))
                else:
                    conn.execute("UPDATE bets SET status = 'lost' WHERE id = ?", (b['id'],))
        conn.commit()
    return "Results checked and balance updated", 200
