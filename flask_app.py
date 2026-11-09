from flask import Flask, request, render_template_string, session, redirect, url_for
import sqlite3, os, random, requests
from datetime import datetime, timedelta

app = Flask(__name__)
app.secret_key = "secret_key_123"
db_path = os.path.join(os.path.dirname(__file__), "database.db")
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

def fetch_live_games():
    if not API_KEY: return False
    today = datetime.now().strftime("%Y-%m-%d")
    next_week = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
    headers = {'x-rapidapi-host': "v3.football.api-sports.io", 'x-rapidapi-key': API_KEY}
    
    fixtures = []
    # ליגות: 5 = ליגת האומות (UEFA Nations League), 383 = ליגת העל, 390 = לאומית
    leagues = [5, 383, 390]
    
    for league_id in leagues:
        url = f"https://v3.football.api-sports.io/fixtures?league={league_id}&from={today}&to={next_week}"
        try:
            res = requests.get(url, headers=headers, timeout=5).json()
            fixtures.extend(res.get('response', []))
        except Exception as e:
            print(e)
            
    if not fixtures:
        for league_id in leagues:
            url = f"https://v3.football.api-sports.io/fixtures?league={league_id}&next=10"
            try:
                res = requests.get(url, headers=headers, timeout=5).json()
                fixtures.extend(res.get('response', []))
            except Exception as e:
                print(e)

    with get_db() as conn:
        conn.execute("DELETE FROM games WHERE status = 'open'")
        if fixtures:
            for idx, g in enumerate(fixtures[:15], start=1):
                t1, t2 = g['teams']['home']['name'], g['teams']['away']['name']
                l1, l2 = g['teams']['home']['logo'], g['teams']['away']['logo']
                o1, ox, o2 = round(random.uniform(1.8, 2.5), 2), round(random.uniform(2.8, 3.5), 2), round(random.uniform(2.0, 3.0), 2)
                conn.execute("INSERT INTO games (id, team1, team2, logo1, logo2, odd_1, odd_x, odd_2, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'open')", (idx, t1, t2, l1, l2, o1, ox, o2))
        conn.commit()
    return len(fixtures) > 0

init_db()

HTML = """<!DOCTYPE html>
<html dir="rtl" lang="he">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ווינר חברים</title>
<style>
body { font-family: sans-serif; text-align: center; background: #1e3c72; color: #fff; padding: 10px; }
.card { background: #fff; color: #333; padding: 15px; margin: 10px auto; max-width: 500px; border-radius: 8px; }
button { background: #ff4757; color: white; border: none; padding: 8px 15px; border-radius: 5px; cursor: pointer; font-weight: bold; width: 100%; margin-top: 5px; }
input { padding: 8px; margin: 5px; border: 1px solid #ccc; border-radius: 5px; }
.nav a { color: white; margin: 0 10px; font-weight: bold; text-decoration: none; }
.team-logo { width: 40px; height: 40px; vertical-align: middle; }
.alert { background: #ff4757; color: white; padding: 10px; border-radius: 5px; margin: 10px; }
</style>
</head>
<body>
<h1>ווינר חברים ⚽</h1>
{% if error_msg %}<div class="alert">{{ error_msg }}</div>{% endif %}
{% if not user %}
<div class="card">
  <h2>התחברות</h2>
  <form method="POST" action="/login">
    <input type="text" name="username" placeholder="שם משתמש" required>
    <button type="submit">היכנס</button>
  </form>
</div>
{% else %}
<div class="nav">
  <a href="/">משחקים</a> | <a href="/league">טבלה</a> | <a href="/history">היסטוריה</a> | <a href="/logout">יציאה</a>
</div>
<h3>שלום {{ user }} | יתרה: {{ balance }} ₪</h3>

{% if view == 'games' %}
  {% if not games %}
    <div class="card"><h3>אין משחקים בשבוע הקרוב</h3></div>
  {% endif %}
  {% for g in games %}
  <div class="card">
    <div><img src="{{ g['logo1'] }}" class="team-logo"> {{ g['team1'] }} VS {{ g['team2'] }} <img src="{{ g['logo2'] }}" class="team-logo"></div>
    <form method="POST" action="/bet">
      <input type="hidden" name="game_id" value="{{ g['id'] }}">
      <label><input type="radio" name="guess" value="1" required> 1 ({{ g['odd_1'] }})</label>
      <label><input type="radio" name="guess" value="X"> X ({{ g['odd_x'] }})</label>
      <label><input type="radio" name="guess" value="2"> 2 ({{ g['odd_2'] }})</label><br>
      <input type="number" name="amount" placeholder="סכום" min="1" max="{{ balance }}" required>
      <button type="submit">שלח הימור</button>
    </form>
  </div>
  {% endfor %}
{% elif view == 'league' %}
  <div class="card">
    <h2>טבלת הליגה</h2>
    {% for u in users_league %}<p>{{ loop.index }}. {{ u['name'] }} - {{ u['balance'] }} ₪</p>{% endfor %}
  </div>
{% elif view == 'history' %}
  <div class="card">
    <h2>ההימורים שלי</h2>
    {% for b in user_bets %}<p>{{ b['team1'] }} - {{ b['team2'] }} | הימור: {{ b['guess'] }} | סכום: {{ b['amount'] }} | סטטוס: {{ b['status'] }}</p>{% endfor %}
  </div>
{% endif %}
{% endif %}
</body>
</html>"""

@app.route("/")
def index():
    user = session.get("user")
    error_msg = "כבר הימרת על המשחק הזה!" if request.args.get("error") == "already_bet" else None
    if not user: return render_template_string(HTML, user=None)
    with get_db() as conn:
        row = conn.execute("SELECT balance FROM users WHERE name = ?", (user,)).fetchone()
        if not row: session.clear(); return redirect("/")
        games = conn.execute("SELECT * FROM games WHERE status = 'open'").fetchall()
        return render_template_string(HTML, user=user, balance=row["balance"], games=games, view='games', error_msg=error_msg)

@app.route("/league")
def league():
    user = session.get("user")
    if not user: return redirect("/")
    with get_db() as conn:
        balance = conn.execute("SELECT balance FROM users WHERE name = ?", (user,)).fetchone()["balance"]
        users = conn.execute("SELECT name, balance FROM users ORDER BY balance DESC").fetchall()
        return render_template_string(HTML, user=user, balance=balance, users_league=users, view='league')

@app.route("/history")
def history():
    user = session.get("user")
    if not user: return redirect("/")
    with get_db() as conn:
        balance = conn.execute("SELECT balance FROM users WHERE name = ?", (user,)).fetchone()["balance"]
        bets = conn.execute("SELECT b.guess, b.amount, b.status, g.team1, g.team2 FROM bets b JOIN games g ON b.game_id = g.id WHERE b.user = ? ORDER BY b.id DESC", (user,)).fetchall()
        return render_template_string(HTML, user=user, balance=balance, user_bets=bets, view='history')

@app.route("/login", methods=["POST"])
def login():
    user = request.form.get("username", "").strip()
    if user:
        session["user"] = user
        with get_db() as conn:
            if not conn.execute("SELECT name FROM users WHERE name = ?", (user,)).fetchone():
                conn.execute("INSERT INTO users (name, balance) VALUES (?, 1000)", (user,))
                conn.commit()
    return redirect("/")

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

@app.route("/bet", methods=["POST"])
def bet():
    user = session.get("user")
    amount, game_id, guess = int(request.form.get("amount", 0)), int(request.form.get("game_id")), request.form.get("guess")
    if user and amount > 0:
        with get_db() as conn:
            if conn.execute("SELECT id FROM bets WHERE user = ? AND game_id = ?", (user, game_id)).fetchone():
                return redirect("/?error=already_bet")
            bal = conn.execute("SELECT balance FROM users WHERE name = ?", (user,)).fetchone()["balance"]
            if bal >= amount:
                conn.execute("UPDATE users SET balance = balance - ? WHERE name = ?", (amount, user))
                conn.execute("INSERT INTO bets (user, game_id, guess, amount, timestamp, status) VALUES (?, ?, ?, ?, ?, 'pending')", (user, game_id, guess, amount, datetime.now().strftime("%Y-%m-%d %H:%M")))
                conn.commit()
    return redirect("/history")

@app.route("/update_live")
def update_live():
    found = fetch_live_games()
    return f"Games updated. Live games found: {found}", 200
