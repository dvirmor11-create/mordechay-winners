import os
import re
import sqlite3
import secrets
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests
from flask import (
    Flask, request, render_template_string, redirect, url_for,
    session, flash, abort
)

# -------------------- Configuration --------------------

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("DATABASE_PATH", os.path.join(BASE_DIR, "winner_friends.db"))
API_KEY = os.environ.get("API_FOOTBALL_KEY", "").strip()
SECRET_KEY = os.environ.get("FLASK_SECRET_KEY", "").strip()
ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN", "").strip()
API_BASE = "https://v3.football.api-sports.io"
LOCAL_TZ = ZoneInfo("Asia/Jerusalem")

if not SECRET_KEY:
    # Works for local testing, but set a persistent secret in production.
    SECRET_KEY = secrets.token_hex(32)
    logging.warning("FLASK_SECRET_KEY is not set. Sessions may be invalidated after restart.")

app = Flask(__name__)
app.secret_key = SECRET_KEY
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    # Enable only when deploying behind HTTPS:
    SESSION_COOKIE_SECURE=os.environ.get("COOKIE_SECURE", "0") == "1",
)

ALLOWED_LEAGUES = {
    383: "ליגת העל בישראל",
    390: "הליגה הלאומית בישראל",
    140: "לה ליגה",
    39: "פרמייר ליג",
    5: "ליגת האומות",
    2: "ליגת האלופות",
    3: "הליגה האירופית",
    848: "קונפרנס ליג",
}

TRANSLATIONS = {
    # ישראל
    "Maccabi Tel Aviv": "מכבי תל אביב", "Maccabi Haifa": "מכבי חיפה",
    "Hapoel Beer Sheva": "הפועל באר שבע", "Hapoel Be'er Sheva": "הפועל באר שבע",
    "Beitar Jerusalem": 'בית"ר ירושלים', "Hapoel Tel Aviv": "הפועל תל אביב",
    "Maccabi Netanya": "מכבי נתניה", "Hapoel Haifa": "הפועל חיפה",
    "Bnei Sakhnin": "בני סכנין", "Hapoel Jerusalem": "הפועל ירושלים",
    "Maccabi Bnei Raina": "מכבי בני ריינה", "Hapoel Hadera": "הפועל חדרה",
    "Ironi Kiryat Shmona": "עירוני קריית שמונה", "Maccabi Petah Tikva": "מכבי פתח תקווה",
    "F.C. Ashdod": "מ.ס. אשדוד", "FC Ashdod": "מ.ס. אשדוד",
    "Hapoel Petah Tikva": "הפועל פתח תקווה", "Bnei Yehuda": "בני יהודה",
    "Hapoel Kfar Saba": "הפועל כפר סבא", "Hapoel Ramat Gan": "הפועל רמת גן",
    "Hapoel Rishon LeZion": "הפועל ראשון לציון", "Hapoel Afula": "הפועל עפולה",
    "Hapoel Umm al-Fahm": "הפועל אום אל-פחם", "Maccabi Jaffa": "מכבי יפו",
    "Hapoel Nir Ramat HaSharon": "הפועל רמת השרון", "Ironi Tiberias": "עירוני טבריה",
    "Maccabi Herzliya": "מכבי הרצליה", "Sektzia Nes Tziona": "סקציית נס ציונה",
    "Hapoel Nof HaGalil": "הפועל נוף הגליל",
    # ספרד
    "Real Madrid": "ריאל מדריד", "Barcelona": "ברצלונה",
    "Atletico Madrid": "אתלטיקו מדריד", "Atlético Madrid": "אתלטיקו מדריד",
    "Sevilla": "סביליה", "Villarreal": "ויאריאל",
    "Real Sociedad": "ריאל סוסיאדד", "Girona": "ג'ירונה",
    "Real Betis": "ריאל בטיס", "Athletic Club": "אתלטיק בילבאו",
    "Valencia": "ולנסיה", "Getafe": "חטאפה",
    # אנגליה
    "Arsenal": "ארסנל", "Manchester City": "מנצ'סטר סיטי",
    "Manchester United": "מנצ'סטר יונייטד", "Liverpool": "ליברפול",
    "Chelsea": "צ'לסי", "Tottenham": "טוטנהאם",
    "Tottenham Hotspur": "טוטנהאם", "Aston Villa": "אסטון וילה",
    "Newcastle": "ניוקאסל", "Newcastle United": "ניוקאסל",
    "West Ham": "ווסטהאם", "West Ham United": "ווסטהאם",
    "Everton": "אברטון", "Brighton": "ברייטון",
    "Brighton and Hove Albion": "ברייטון", "Crystal Palace": "קריסטל פאלאס",
    "Wolverhampton Wanderers": "וולבס", "Wolves": "וולבס",
    "Nottingham Forest": "נוטינגהאם פורסט", "Leicester": "לסטר",
    # נבחרות
    "Israel": "ישראל", "France": "צרפת", "Italy": "איטליה",
    "Belgium": "בלגיה", "Spain": "ספרד", "England": "אנגליה",
    "Germany": "גרמניה", "Portugal": "פורטוגל", "Netherlands": "הולנד",
    "Croatia": "קרואטיה", "Brazil": "ברזיל", "Argentina": "ארגנטינה",
}

def translate_team(name):
    name = (name or "").strip()
    if name in TRANSLATIONS:
        return TRANSLATIONS[name]
    cleaned = re.sub(r"\b(FC|F\.C\.|CF|C\.F\.|AFC|Club)\b", "", name, flags=re.I)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" -")
    return TRANSLATIONS.get(cleaned, cleaned or name)

# -------------------- Database --------------------

def db():
    conn = sqlite3.connect(DB_PATH, timeout=20)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn

def init_db():
    with db() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            name TEXT PRIMARY KEY COLLATE NOCASE,
            balance REAL NOT NULL DEFAULT 1000 CHECK(balance >= 0),
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS games (
            fixture_id INTEGER PRIMARY KEY,
            league_id INTEGER NOT NULL,
            league_name TEXT NOT NULL,
            season INTEGER,
            home_name TEXT NOT NULL,
            away_name TEXT NOT NULL,
            home_logo TEXT,
            away_logo TEXT,
            kickoff_utc TEXT,
            kickoff_local TEXT,
            odd_1 REAL NOT NULL,
            odd_x REAL NOT NULL,
            odd_2 REAL NOT NULL,
            odds_real INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'open',
            result TEXT,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS bets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_name TEXT NOT NULL COLLATE NOCASE,
            fixture_id INTEGER NOT NULL,
            guess TEXT NOT NULL CHECK(guess IN ('1','X','2')),
            amount REAL NOT NULL CHECK(amount > 0),
            odds_at_bet REAL NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            payout REAL NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            UNIQUE(user_name, fixture_id),
            FOREIGN KEY(user_name) REFERENCES users(name),
            FOREIGN KEY(fixture_id) REFERENCES games(fixture_id)
        );
        CREATE INDEX IF NOT EXISTS idx_bets_user ON bets(user_name, created_at);
        CREATE INDEX IF NOT EXISTS idx_games_status ON games(status);
        """)
        conn.commit()

def now_iso():
    return datetime.now(LOCAL_TZ).isoformat(timespec="seconds")

# -------------------- API-Football --------------------

def api_headers():
    if not API_KEY:
        raise RuntimeError("לא הוגדר API_FOOTBALL_KEY במשתני הסביבה")
    return {"x-apisports-key": API_KEY}

def api_get(path, params):
    response = requests.get(
        f"{API_BASE}{path}", headers=api_headers(), params=params, timeout=20
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("errors"):
        raise RuntimeError(f"API-Football error: {payload['errors']}")
    return payload.get("response", [])

def match_winner_odds(fixture_id):
    """Return (home, draw, away, is_real). 9.99 is only a clearly marked fallback."""
    try:
        data = api_get("/odds", {"fixture": fixture_id, "bet": 1})
        best = None
        # Prefer a bookmaker that supplies all three outcomes; otherwise try the next.
        for item in data:
            for bookmaker in item.get("bookmakers", []):
                for market in bookmaker.get("bets", []):
                    if market.get("id") != 1 and market.get("name", "").lower() != "match winner":
                        continue
                    values = {}
                    for entry in market.get("values", []):
                        label = str(entry.get("value", "")).strip().lower()
                        try:
                            odd = float(entry.get("odd"))
                        except (TypeError, ValueError):
                            continue
                        if label in ("home", "1"):
                            values["1"] = odd
                        elif label in ("draw", "x"):
                            values["X"] = odd
                        elif label in ("away", "2"):
                            values["2"] = odd
                    if all(k in values and values[k] > 1 for k in ("1", "X", "2")):
                        best = (values["1"], values["X"], values["2"], True)
                        break
                if best:
                    break
            if best:
                break
        return best or (9.99, 9.99, 9.99, False)
    except (requests.RequestException, ValueError, RuntimeError) as exc:
        app.logger.warning("Odds unavailable for fixture %s: %s", fixture_id, exc)
        return 9.99, 9.99, 9.99, False

def fetch_live_games(days=7):
    """Fetch upcoming fixtures, then enforce the allow-list before saving anything."""
    if not API_KEY:
        return 0, "חסר API_FOOTBALL_KEY בהגדרות הסביבה"

    fixtures = {}
    today = datetime.now(LOCAL_TZ).date()
    errors = []
    for offset in range(days):
        date_text = (today + timedelta(days=offset)).isoformat()
        try:
            for item in api_get("/fixtures", {"date": date_text, "timezone": "Asia/Jerusalem"}):
                league_id = item.get("league", {}).get("id")
                fixture_id = item.get("fixture", {}).get("id")
                status = item.get("fixture", {}).get("status", {}).get("short")
                if league_id in ALLOWED_LEAGUES and fixture_id and status == "NS":
                    fixtures[fixture_id] = item
        except Exception as exc:
            errors.append(f"{date_text}: {exc}")
            app.logger.warning("Fixture fetch failed for %s: %s", date_text, exc)

    if not fixtures:
        suffix = (" שגיאות: " + "; ".join(errors[:2])) if errors else ""
        return 0, "לא נמצאו משחקים עתידיים בליגות המאושרות." + suffix

    count = 0
    with db() as conn:
        for fixture_id, item in fixtures.items():
            league = item.get("league", {})
            home = item.get("teams", {}).get("home", {})
            away = item.get("teams", {}).get("away", {})
            fixture = item.get("fixture", {})
            if league.get("id") not in ALLOWED_LEAGUES:
                continue

            raw_kickoff = fixture.get("date")
            try:
                dt = datetime.fromisoformat(raw_kickoff.replace("Z", "+00:00"))
                kickoff_local = dt.astimezone(LOCAL_TZ).strftime("%d/%m/%Y %H:%M")
            except Exception:
                kickoff_local = ""

            o1, ox, o2, is_real = match_winner_odds(fixture_id)
            conn.execute("""
                INSERT INTO games (
                    fixture_id, league_id, league_name, season,
                    home_name, away_name, home_logo, away_logo,
                    kickoff_utc, kickoff_local, odd_1, odd_x, odd_2,
                    odds_real, status, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'open', ?)
                ON CONFLICT(fixture_id) DO UPDATE SET
                    league_id=excluded.league_id,
                    league_name=excluded.league_name,
                    season=excluded.season,
                    home_name=excluded.home_name,
                    away_name=excluded.away_name,
                    home_logo=excluded.home_logo,
                    away_logo=excluded.away_logo,
                    kickoff_utc=excluded.kickoff_utc,
                    kickoff_local=excluded.kickoff_local,
                    odd_1=excluded.odd_1,
                    odd_x=excluded.odd_x,
                    odd_2=excluded.odd_2,
                    odds_real=excluded.odds_real,
                    updated_at=excluded.updated_at
                WHERE games.status='open'
            """, (
                fixture_id, league["id"], ALLOWED_LEAGUES[league["id"]],
                league.get("season"), translate_team(home.get("name")),
                translate_team(away.get("name")), home.get("logo"), away.get("logo"),
                raw_kickoff, kickoff_local, o1, ox, o2, int(is_real), now_iso()
            ))
            count += 1
        conn.commit()
    return count, f"עודכנו {count} משחקים מהליגות המאושרות בלבד."

# -------------------- Helpers / access --------------------

def current_user():
    return session.get("user")

def require_login():
    if not current_user():
        return redirect(url_for("index"))
    return None

def require_admin():
    if not session.get("is_admin"):
        abort(403)

def render_page(view, **kwargs):
    user = current_user()
    balance = None
    if user:
        with db() as conn:
            row = conn.execute("SELECT balance FROM users WHERE name=?", (user,)).fetchone()
            balance = row["balance"] if row else 0
    return render_template_string(
        PAGE, view=view, user=user, balance=balance,
        allowed_leagues=ALLOWED_LEAGUES, **kwargs
    )

# -------------------- HTML --------------------

PAGE = r"""
<!doctype html>
<html lang="he" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ווינר חברים ⚽</title>
<style>
:root{--bg:#101a2b;--card:#fff;--ink:#182235;--accent:#16a085;--red:#e74c3c}
*{box-sizing:border-box}
body{margin:0;padding:14px;background:linear-gradient(135deg,#152744,#263f68);font-family:Arial,system-ui,sans-serif;color:#fff}
main{max-width:760px;margin:auto}
h1{text-align:center;margin:12px 0 18px}
nav{display:flex;flex-wrap:wrap;gap:7px;justify-content:center;margin:12px 0}
nav a,.btn{background:#294b72;color:#fff;text-decoration:none;border:0;border-radius:9px;padding:10px 13px;font-weight:bold;cursor:pointer}
.card{background:var(--card);color:var(--ink);border-radius:15px;padding:15px;margin:12px auto;box-shadow:0 5px 18px #0003}
.center{text-align:center}
input,select{padding:11px;border:1px solid #ccd3dc;border-radius:8px;max-width:100%;font-size:16px}
button{font-size:15px}
.btn-primary{background:var(--accent);width:100%;margin-top:10px}
.btn-danger{background:var(--red)}
.balance{text-align:center;font-weight:bold;margin:10px}
.match-top{display:flex;justify-content:space-between;gap:8px;align-items:center;color:#566}
.match-header{display:flex;direction:ltr;align-items:center;justify-content:space-between;gap:5px;margin:16px 0}
.team{display:flex;align-items:center;gap:6px;flex:1;min-width:0}
.team.home{justify-content:flex-start;text-align:left}
.team.away{justify-content:flex-end;text-align:right}
.team img{width:38px;height:38px;object-fit:contain;flex-shrink:0}
.team b{font-size:14px;overflow-wrap:anywhere}
.vs{font-weight:bold;color:#e74c3c}
.odds{display:flex;gap:7px;justify-content:space-between;margin:12px 0}
.odds label{flex:1;border:1px solid #d8dee8;border-radius:9px;padding:9px 3px;text-align:center;font-weight:bold}
.odds input{width:auto}
.fallback{background:#fff0d5;color:#8a5200;border-radius:8px;padding:8px;font-size:13px;text-align:center}
small,.muted{color:#687386}
table{width:100%;border-collapse:collapse;color:#182235}
td,th{padding:10px 5px;border-bottom:1px solid #e5e9ef;text-align:center}
.notice{padding:11px;border-radius:9px;background:#e8f6f3;color:#12614f;margin:10px 0}
.error{background:#fdecea;color:#922b21}
.status-won{color:#14845f;font-weight:bold}.status-lost{color:#c0392b;font-weight:bold}.status-pending{color:#a66b00;font-weight:bold}
@media(max-width:420px){body{padding:9px}.card{padding:12px}.team img{width:31px;height:31px}.team b{font-size:12px}.odds label{font-size:13px}}
</style>
</head>
<body><main>
<h1>ווינר חברים ⚽</h1>
{% with messages=get_flashed_messages(with_categories=true) %}
{% for category,message in messages %}<div class="card notice {{ 'error' if category=='error' else '' }}">{{ message }}</div>{% endfor %}
{% endwith %}

{% if not user %}
<div class="card center">
<h2>כניסה למשחק</h2>
<p>בחר שם משתמש. אין צורך בסיסמה.</p>
<form method="post" action="{{ url_for('login') }}">
<input name="username" maxlength="24" minlength="2" placeholder="שם משתמש" required>
<button class="btn btn-primary" type="submit">כניסה</button>
</form>
</div>
{% else %}
<nav>
<a href="{{ url_for('index') }}">משחקים</a>
<a href="{{ url_for('league') }}">טבלת חברים</a>
<a href="{{ url_for('history') }}">ההימורים שלי</a>
<a href="{{ url_for('logout') }}">יציאה</a>
{% if session.get('is_admin') %}<a href="{{ url_for('admin') }}">ניהול</a>{% endif %}
</nav>
<div class="balance">שלום {{ user }} · יתרה: {{ '%.2f'|format(balance) }} ₪</div>

{% if view=='games' %}
{% if games %}
{% for g in games %}
<div class="card">
<div class="match-top"><small>{{ g['league_name'] }}</small><small>{{ g['kickoff_local'] or 'מועד לא ידוע' }}</small></div>
<div class="match-header">
<div class="team home"><img src="{{ g['home_logo'] or '' }}" alt=""><b>{{ g['home_name'] }}</b></div>
<div class="vs">VS</div>
<div class="team away"><b>{{ g['away_name'] }}</b><img src="{{ g['away_logo'] or '' }}" alt=""></div>
</div>
{% if not g['odds_real'] %}<div class="fallback">⚠ יחס לא זמין מהסוכנויות — 9.99 / 9.99 / 9.99 (יחס ברירת מחדל, לא יחס אמיתי)</div>{% endif %}
<form method="post" action="{{ url_for('bet') }}">
<input type="hidden" name="fixture_id" value="{{ g['fixture_id'] }}">
<div class="odds">
<label><input type="radio" name="guess" value="1" required><br>1<br>{{ '%.2f'|format(g['odd_1']) }}</label>
<label><input type="radio" name="guess" value="X"><br>X<br>{{ '%.2f'|format(g['odd_x']) }}</label>
<label><input type="radio" name="guess" value="2"><br>2<br>{{ '%.2f'|format(g['odd_2']) }}</label>
</div>
<input type="number" name="amount" min="1" max="{{ balance }}" step="1" placeholder="סכום ההימור בש״ח" required style="width:100%">
<button class="btn btn-primary" type="submit">שליחת הימור</button>
</form>
</div>
{% endfor %}
{% else %}<div class="card center">אין כרגע משחקים פתוחים. בקש ממנהל לעדכן משחקים.</div>{% endif %}

{% elif view=='league' %}
<div class="card"><h2 class="center">טבלת החברים 🏆</h2>
<table><tr><th>דירוג</th><th>שם</th><th>יתרה</th></tr>
{% for u in users %}<tr><td>{{ loop.index }}</td><td>{{ u['name'] }}</td><td>{{ '%.2f'|format(u['balance']) }} ₪</td></tr>{% endfor %}
</table></div>

{% elif view=='history' %}
<div class="card"><h2>היסטוריית ההימורים שלי</h2>
{% if bets %}
<table><tr><th>משחק</th><th>בחירה</th><th>סכום</th><th>יחס</th><th>סטטוס</th><th>זכייה</th></tr>
{% for b in bets %}
<tr><td>{{ b['home_name'] }} – {{ b['away_name'] }}</td><td>{{ b['guess'] }}</td><td>{{ '%.2f'|format(b['amount']) }}</td><td>{{ '%.2f'|format(b['odds_at_bet']) }}</td>
<td class="status-{{ b['status'] }}">{{ {'pending':'ממתין','won':'זכייה','lost':'הפסד'}.get(b['status'],b['status']) }}</td>
<td>{{ '%.2f'|format(b['payout']) }} ₪</td></tr>
{% endfor %}</table>
{% else %}<p>עדיין אין הימורים.</p>{% endif %}
</div>
{% elif view=='admin' %}
<div class="card"><h2>ניהול מערכת</h2>
<form method="post" action="{{ url_for('admin_update') }}"><button class="btn btn-primary">משיכת משחקים ויחסים מה-API</button></form>
<form method="post" action="{{ url_for('admin_results') }}" onsubmit="return confirm('להגריל תוצאות לכל המשחקים הפתוחים? פעולה זו אינה הפיכה.');">
<button class="btn btn-danger" style="width:100%;margin-top:10px">הגרלת תוצאות וסגירת משחקים</button></form>
<p class="muted">הגרלת התוצאות היא לצורכי משחק חברתי בלבד ואינה תוצאת המשחק האמיתית.</p>
</div>
{% endif %}
{% endif %}
</main></body></html>
"""

# -------------------- Routes --------------------

@app.get("/")
def index():
    if not current_user():
        return render_page("login")
    with db() as conn:
        games = conn.execute("""
            SELECT * FROM games
            WHERE status='open' AND kickoff_utc IS NOT NULL
            ORDER BY kickoff_utc ASC
        """).fetchall()
    return render_page("games", games=games)

@app.post("/login")
def login():
    username = re.sub(r"\s+", " ", request.form.get("username", "")).strip()
    if not 2 <= len(username) <= 24:
        flash("שם המשתמש חייב להכיל 2–24 תווים.", "error")
        return redirect(url_for("index"))
    if any(ord(c) < 32 for c in username):
        flash("שם משתמש לא תקין.", "error")
        return redirect(url_for("index"))
    with db() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO users(name,balance,created_at) VALUES(?,1000,?)",
            (username, now_iso())
        )
        conn.commit()
        actual = conn.execute("SELECT name FROM users WHERE name=? COLLATE NOCASE", (username,)).fetchone()
    session.clear()
    session["user"] = actual["name"]
    flash("נכנסת בהצלחה. משתמש חדש מתחיל עם 1,000 ₪.", "success")
    return redirect(url_for("index"))

@app.get("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))

@app.post("/bet")
def bet():
    if not current_user():
        return redirect(url_for("index"))
    try:
        fixture_id = int(request.form.get("fixture_id", ""))
        amount = float(request.form.get("amount", "0"))
    except (TypeError, ValueError):
        flash("נתוני ההימור אינם תקינים.", "error")
        return redirect(url_for("index"))
    guess = request.form.get("guess")
    if guess not in ("1", "X", "2") or amount <= 0 or not amount.is_integer():
        flash("יש לבחור תוצאה ולהזין סכום שלם וחיובי.", "error")
        return redirect(url_for("index"))

    with db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        game = conn.execute("SELECT * FROM games WHERE fixture_id=? AND status='open'", (fixture_id,)).fetchone()
        user = conn.execute("SELECT balance FROM users WHERE name=?", (current_user(),)).fetchone()
        if not game:
            conn.rollback()
            flash("המשחק אינו פתוח להימורים.", "error")
            return redirect(url_for("index"))
        if not user or user["balance"] < amount:
            conn.rollback()
            flash("אין יתרה מספקת להימור הזה.", "error")
            return redirect(url_for("index"))
        odd = {"1": game["odd_1"], "X": game["odd_x"], "2": game["odd_2"]}[guess]
        try:
            conn.execute(
                "INSERT INTO bets(user_name,fixture_id,guess,amount,odds_at_bet,created_at) VALUES(?,?,?,?,?,?)",
                (current_user(), fixture_id, guess, amount, odd, now_iso())
            )
        except sqlite3.IntegrityError:
            conn.rollback()
            flash("כבר ביצעת הימור על המשחק הזה.", "error")
            return redirect(url_for("index"))
        conn.execute("UPDATE users SET balance=balance-? WHERE name=?", (amount, current_user()))
        conn.commit()
    flash("ההימור נשמר בהצלחה.", "success")
    return redirect(url_for("index"))

@app.get("/league")
def league():
    denied = require_login()
    if denied:
        return denied
    with db() as conn:
        users = conn.execute("SELECT name,balance FROM users ORDER BY balance DESC,name ASC").fetchall()
    return render_page("league", users=users)

@app.get("/history")
def history():
    denied = require_login()
    if denied:
        return denied
    with db() as conn:
        bets = conn.execute("""
            SELECT b.*,g.home_name,g.away_name
            FROM bets b JOIN games g ON g.fixture_id=b.fixture_id
            WHERE b.user_name=? ORDER BY b.id DESC
        """, (current_user(),)).fetchall()
    return render_page("history", bets=bets)

@app.route("/admin", methods=["GET", "POST"])
def admin():
    if request.method == "POST":
        supplied = request.form.get("admin_token", "")
        if not ADMIN_TOKEN or not secrets.compare_digest(supplied, ADMIN_TOKEN):
            flash("אסימון מנהל שגוי או שלא הוגדר.", "error")
            return redirect(url_for("admin"))
        session["is_admin"] = True
        return redirect(url_for("admin"))
    if not session.get("is_admin"):
        return render_template_string("""
        <!doctype html><html lang="he" dir="rtl"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
        <body style="font-family:Arial;max-width:420px;margin:40px auto;padding:15px">
        <h2>כניסת מנהל</h2><form method="post"><input type="password" name="admin_token" placeholder="אסימון מנהל" required style="width:100%;padding:12px;box-sizing:border-box">
        <button style="margin-top:10px;padding:12px;width:100%">כניסה</button></form></body></html>
        """)
    return render_page("admin")

@app.post("/admin/update")
def admin_update():
    require_admin()
    count, message = fetch_live_games()
    flash(message, "success" if count else "error")
    return redirect(url_for("admin"))

@app.post("/admin/results")
def admin_results():
    require_admin()
    with db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        games = conn.execute("SELECT * FROM games WHERE status='open'").fetchall()
        import random
        for game in games:
            result = secrets.choice(("1", "X", "2"))
            conn.execute(
                "UPDATE games SET status='closed',result=? WHERE fixture_id=? AND status='open'",
                (result, game["fixture_id"])
            )
            bets = conn.execute(
                "SELECT * FROM bets WHERE fixture_id=? AND status='pending'",
                (game["fixture_id"],)
            ).fetchall()
            for bet_row in bets:
                if bet_row["guess"] == result:
                    payout = round(bet_row["amount"] * bet_row["odds_at_bet"], 2)
                    conn.execute("UPDATE users SET balance=balance+? WHERE name=?", (payout, bet_row["user_name"]))
                    conn.execute("UPDATE bets SET status='won',payout=? WHERE id=?", (payout, bet_row["id"]))
                else:
                    conn.execute("UPDATE bets SET status='lost',payout=0 WHERE id=?", (bet_row["id"],))
        conn.commit()
    flash(f"הוגרלו תוצאות ונסגרו {len(games)} משחקים.", "success")
    return redirect(url_for("admin"))

@app.get("/health")
def health():
    return {"status": "ok"}

@app.errorhandler(403)
def forbidden(_):
    return "אין הרשאה לפעולה זו.", 403

@app.errorhandler(404)
def not_found(_):
    return "העמוד לא נמצא.", 404

init_db()

if __name__ == "__main__":
    # For local development only. Use a production WSGI server when deploying publicly.
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5000")), debug=False)
