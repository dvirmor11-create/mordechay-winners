from flask import Flask, request, render_template_string, session, redirect, url_for
import sqlite3, os, requests, re
from datetime import datetime, timedelta, timezone

app = Flask(__name__)
app.secret_key = "secret_key_123"
db_path = os.path.join(os.path.dirname(__file__), "database.db")
API_KEY = "e82bd0d32359350788242541846dc07a"

# 383: ליגת העל | 390: הליגה הלאומית | 140: לה ליגה | 39: פרמייר ליג | 5: ליגת האומות | 2: צ'מפיונס | 3: אירופית | 848: קונפרנס
ALLOWED_LEAGUES = [383, 390, 140, 39, 5, 2, 3, 848]

# מילון תרגום שמות קבוצות מאנגלית לעברית
TRANSLATIONS_MAP = {
    # ליגות בישראל
    "Maccabi Tel Aviv": "מכבי תל אביב", "Maccabi Haifa": "מכבי חיפה", "Hapoel Beer Sheva": "הפועל באר שבע",
    "Beitar Jerusalem": "בית\"ר ירושלים", "Hapoel Tel Aviv": "הפועל תל אביב", "Maccabi Netanya": "מכבי נתניה",
    "Hapoel Haifa": "הפועל חיפה", "Bnei Sakhnin": "בני סכנין", "Hapoel Jerusalem": "הפועל ירושלים",
    "Maccabi Bnei Raina": "מכבי בני ריינה", "Hapoel Hadera": "הפועל חדרה", "Ironi Kiryat Shmona": "עירוני קריית שמונה",
    "Maccabi Petah Tikva": "מכבי פתח תקווה", "F.C. Ashdod": "מ.ס. אשדוד", "Hapoel Petah Tikva": "הפועל פתח תקווה",
    "Bnei Yehuda": "בני יהודה", "Hapoel Kfar Saba": "הפועל כפר סבא", "Hapoel Ramat Gan": "הפועל רמת גן",
    "Hapoel Rishon LeZion": "הפועל ראשון לציון", "Hapoel Afula": "הפועל עפולה", "Hapoel Umm al-Fahm": "הפועל אום אל-פחם",
    "Maccabi Jaffa": "מכבי יפו", "Hapoel Nir Ramat HaSharon": "הפועל רמת השרון", "Ironi Tiberias": "עירוני טבריה",
    "Maccabi Herzliya": "מכבי הרצליה", "Sektzia Nes Tziona": "סקציית נס ציונה", "Hapoel Nof HaGalil": "הפועל נוף הגליל",
    
    # אנגליה & ספרד
    "Real Madrid": "ריאל מדריד", "Barcelona": "ברצלונה", "Atletico Madrid": "אתלטיקו מדריד", "Sevilla": "סביליה",
    "Villarreal": "ויאריאל", "Real Sociedad": "ריאל סוסיאדד", "Girona": "ג'ירונה", "Real Betis": "ריאל בטיס",
    "Arsenal": "ארסנל", "Manchester City": "מנצ'סטר סיטי", "Liverpool": "ליברפול", "Chelsea": "צ'לסי",
    "Tottenham": "טוטנהאם", "Manchester United": "מנצ'סטר יונייטד", "Aston Villa": "אסטון וילה", "Newcastle": "ניוקאסל",
    
    # נבחרות (ליגת האומות)
    "Israel": "ישראל", "France": "צרפת", "Italy": "איטליה", "Belgium": "בלגיה", "Spain": "ספרד",
    "England": "אנגליה", "Germany": "גרמניה", "Portugal": "פורטוגל", "Netherlands": "הולנד", "Croatia": "קרואטיה"
}

def translate_team(team_name):
    """מתרגם את שם הקבוצה לעברית במידה וקיים במילון"""
    if team_name in TRANSLATIONS_MAP:
        return TRANSLATIONS_MAP[team_name]
    # תרגום בסיסי למקרים ששם הקבוצה מכיל סיומות נפוצות
    clean_name = re.sub(r'\b(FC|F\.C\.|Club|Town|City|United)\b', '', team_name, flags=re.IGNORECASE).strip()
    return TRANSLATIONS_MAP.get(clean_name, team_name)

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

    filtered_fixtures = [g for g in raw_fixtures if g.get('league', {}).get('id') in ALLOWED_LEAGUES]
    filtered_fixtures.sort(key=lambda g: ALLOWED_LEAGUES.index(g['league']['id']))
    final_fixtures = filtered_fixtures[:10]

    if not final_fixtures:
        return False, "לא נמצאו משחקים עתידיים בליגות המבוקשות בימים הקרובים"

    with get_db() as conn:
        conn.execute("DELETE FROM games WHERE status = 'open'")
        for idx, g in enumerate(final_fixtures, start=1):
            f_id = g['fixture']['id']
            # תרגום שמות הקבוצות לעברית
            t1 = translate_team(g['teams']['home']['name'])
            t2 = translate_team(g['teams']['away']['name'])
            l1, l2 = g['teams']['home']['logo'], g['teams']['away']['logo']
            
            raw_date = g['fixture'].get('date', '')
            try:
                dt = datetime.fromisoformat(raw_date.replace('Z', '+00:00')).astimezone(timezone(timedelta(hours=2)))
                m_time = dt.strftime("%d/%m ב-%H:%M")
            except:
                m_time = ""

            o1, ox, o2 = get_real_odds(f_id, headers)
            if not o1:
                o1, ox, o2 = 9.99, 9.99, 9.99

            conn.execute("INSERT INTO games (id, team1, team2, logo1, logo2, odd_1, odd_x, odd_2, status, match_time) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'open', ?)", 
                         (idx, t1, t2, l1, l2, o1, ox, o2, m_time))
        conn.commit()
    return True, f"נטענו {len(final_fixtures)} משחקים מתורגמים לעברית בהצלחה!"

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
.time-tag { font-size: 0.85em; color: #666; font-weight: bold; background: #f0f0f0; padding: 3px 8px; border-radius: 4px; display: inline-block; }
.alert { background: #ff4757; color: white; padding: 10px; border-radius: 6px; margin: 10px auto; max-width: 480px; font-weight: bold; }
.success { background: #2ed573; color: white; padding: 10px; border-radius: 6px; margin: 10px auto; max-width: 480px; font-weight: bold; }
.status-won { color: #2ed573; font-weight: bold; }
.status-lost { color: #ff4757; font-weight: bold; }
.status-pending { color: #ffa500; font-weight: bold; }
table { width: 100%; border-collapse: collapse; margin-top: 10px; }
th, td { padding: 8px; border-bottom: 1px solid #eee; text-align: center; font-size: 14px; }
</style>
</head>
<body>
<h1>ווינר חברים ⚽</h1>
{% if msg %}<div class="{{ msg_class }}">{{ msg }}</div>{% endif %}

{% if not user %}
<div class="card">
  <h2>התחברות</h2>
  <form method="POST" action="/login">
    <input type="text" name="username" placeholder="שם משתמש" required><br>
    <button type="submit">היכנס למשחק</button>
  </form>
</div>
{% else %}
<div class="nav">
  <a href="/">משחקים</a>
  <a href="/league">טבלה</a>
  <a href="/history">היסטוריה</a>
  <a href="/check_results" onclick="return confirm('להגריל תוצאות ולחלק זכיות?')">עדכן תוצאות</a>
  <a href="/logout" style="background:#ff4757">יציאה</a>
</div>
<h3>שלום {{ user }} | יתרה: {{ balance }} ₪</h3>

{% if view == 'games' %}
  {% if not games %}
    <div class="card"><h3>אין משחקים עתידיים פתוחים כרגע</h3></div>
  {% endif %}
  {% for g in games %}
  <div class="card">
    {% if g['match_time'] %}<div class="time-tag">📅 {{ g['match_time'] }}</div>{% endif %}
    <div class="match-header">
      <div class="team-side home">
        <img src="{{ g['logo1'] }}" class="team-logo">
        <span><b>{{ g['team1'] }}</b></span>
      </div>
      <div class="vs-badge">VS</div>
      <div class="team-side away">
        <span><b>{{ g['team2'] }}</b></span>
        <img src="{{ g['logo2'] }}" class="team-logo">
      </div>
    </div>
    <form method="POST" action="/bet">
      <input type="hidden" name="game_id" value="{{ g['id'] }}">
      <label><input type="radio" name="guess" value="1" required> 1 ({{ g['odd_1'] }})</label>
      <label><input type="radio" name="guess" value="X"> X ({{ g['odd_x'] }})</label>
      <label><input type="radio" name="guess" value="2"> 2 ({{ g['odd_2'] }})</label><br>
      <input type="number" name="amount" placeholder="סכום (₪)" min="1" max="{{ balance }}" required>
      <button type="submit">שלח הימור</button>
    </form>
  </div>
  {% endfor %}
{% elif view == 'league' %}
  <div class="card">
    <h2>טבלת הליגה 🏆</h2>
    <table>
      <tr><th>מיקום</th><th>שם</th><th>יתרה</th></tr>
      {% for u in users_league %}
      <tr><td>{{ loop.index }}</td><td>{{ u['name'] }}</td><td>{{ u['balance'] }} ₪</td></tr>
      {% endfor %}
    </table>
  </div>
{% elif view == 'history' %}
  <div class="card">
    <h2>ההימורים שלי 📜</h2>
    {% if not user_bets %}<p>טרם ביצעת הימורים.</p>{% endif %}
    {% for b in user_bets %}
    <div style="border-bottom:1px solid #eee; padding:8px 0; text-align:right;">
      <b>{{ b['team1'] }} vs {{ b['team2'] }}</b><br>
      הימור: <b>{{ b['guess'] }}</b> | סכום: <b>{{ b['amount'] }} ₪</b> | סטטוס: 
      <span class="status-{{ b['status'] }}">
        {% if b['status'] == 'won' %}זכייה!🏆{% elif b['status'] == 'lost' %}הפסד❌{% else %}ממתין ⏳{% endif %}
      </span>
    </div>
    {% endfor %}
  </div>
{% endif %}
{% endif %}
</body>
</html>"""

@app.route("/")
def index():
    user = session.get("user")
    status_param = request.args.get("msg")
    msg, msg_class = None, "alert"
    if status_param == "already_bet": msg = "כבר הימרת על המשחק הזה!"
    elif status_param == "no_balance": msg = "אין לך מספיק יתרה להימור זה!"
    elif status_param == "bet_placed": msg, msg_class = "ההימור נרשם בהצלחה!", "success"
    elif status_param == "results_checked": msg, msg_class = "תוצאות המשחקים עודכנו והיתרות חושבו!", "success"
    
    if not user: return render_template_string(HTML, user=None, msg=msg, msg_class=msg_class)
    with get_db() as conn:
        row = conn.execute("SELECT balance FROM users WHERE name = ?", (user,)).fetchone()
        if not row: session.clear(); return redirect("/")
        games = conn.execute("SELECT * FROM games WHERE status = 'open'").fetchall()
        return render_template_string(HTML, user=user, balance=row["balance"], games=games, view='games', msg=msg, msg_class=msg_class)

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
    try:
        amount = int(request.form.get("amount", 0))
        game_id = int(request.form.get("game_id"))
    except:
        return redirect("/")
    guess = request.form.get("guess")
    
    if user and amount > 0:
        with get_db() as conn:
            if conn.execute("SELECT id FROM bets WHERE user = ? AND game_id = ?", (user, game_id)).fetchone():
                return redirect("/?msg=already_bet")
            row = conn.execute("SELECT balance FROM users WHERE name = ?", (user,)).fetchone()
            if not row or row["balance"] < amount:
                return redirect("/?msg=no_balance")
            
            conn.execute("UPDATE users SET balance = balance - ? WHERE name = ?", (amount, user))
            conn.execute("INSERT INTO bets (user, game_id, guess, amount, timestamp, status) VALUES (?, ?, ?, ?, ?, 'pending')", 
                         (user, game_id, guess, amount, datetime.now().strftime("%Y-%m-%d %H:%M")))
            conn.commit()
            return redirect("/?msg=bet_placed")
    return redirect("/")

@app.route("/check_results")
def check_results():
    with get_db() as conn:
        open_games = conn.execute("SELECT id, odd_1, odd_x, odd_2 FROM games WHERE status = 'open'").fetchall()
        for g in open_games:
            import random
            result = random.choice(['1', 'X', '2'])
            conn.execute("UPDATE games SET status = 'closed', result = ? WHERE id = ?", (result, g['id']))
            pending_bets = conn.execute("SELECT id, user, amount, guess FROM bets WHERE game_id = ? AND status = 'pending'", (g['id'],)).fetchall()
            for b in pending_bets:
                if str(b['guess']) == result:
                    odd = g['odd_1'] if result == '1' else (g['odd_x'] if result == 'X' else g['odd_2'])
                    win_amount = int(b['amount'] * odd)
                    conn.execute("UPDATE users SET balance = balance + ? WHERE name = ?", (win_amount, b['user']))
                    conn.execute("UPDATE bets SET status = 'won' WHERE id = ?", (b['id'],))
                else:
                    conn.execute("UPDATE bets SET status = 'lost' WHERE id = ?", (b['id'],))
        conn.commit()
    return redirect("/?msg=results_checked")

@app.route("/update_live")
def update_live():
    success, msg = fetch_live_games()
    return f"Status: {msg}", 200
