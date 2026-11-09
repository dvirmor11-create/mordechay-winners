
import os
import re
import sqlite3
import secrets
import logging
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import requests
from flask import (
    Flask, request, render_template_string,
    redirect, url_for, session, flash
)

# ==================================================
# CONFIGURATION
# ==================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DB_PATH = os.path.join(BASE_DIR, "winner_friends.db")

# API KEY FROM THE ORIGINAL GEMINI CODE
API_KEY = "e82bd0d32359350788242541846dc07a"

API_URL = "https://v3.football.api-sports.io"

app = Flask(__name__)
app.secret_key = os.environ.get(
    "FLASK_SECRET_KEY",
    secrets.token_hex(32)
)

app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax"
)

TZ = ZoneInfo("Asia/Jerusalem")

ALLOWED_LEAGUES = {
    383: "ליגת העל בישראל",
    390: "הליגה הלאומית בישראל",
    140: "לה ליגה",
    39: "פרמייר ליג",
    5: "ליגת האומות",
    2: "ליגת האלופות",
    3: "הליגה האירופית",
    848: "קונפרנס ליג"
}

TRANSLATIONS = {
    "Maccabi Tel Aviv": "מכבי תל אביב",
    "Maccabi Haifa": "מכבי חיפה",
    "Hapoel Beer Sheva": "הפועל באר שבע",
    "Hapoel Be'er Sheva": "הפועל באר שבע",
    "Beitar Jerusalem": 'בית"ר ירושלים',
    "Hapoel Tel Aviv": "הפועל תל אביב",
    "Maccabi Netanya": "מכבי נתניה",
    "Hapoel Haifa": "הפועל חיפה",
    "Bnei Sakhnin": "בני סכנין",
    "Hapoel Jerusalem": "הפועל ירושלים",
    "Maccabi Bnei Raina": "מכבי בני ריינה",
    "Hapoel Hadera": "הפועל חדרה",
    "Ironi Kiryat Shmona": "עירוני קריית שמונה",
    "Maccabi Petah Tikva": "מכבי פתח תקווה",
    "F.C. Ashdod": "מ.ס. אשדוד",
    "FC Ashdod": "מ.ס. אשדוד",
    "Hapoel Petah Tikva": "הפועל פתח תקווה",
    "Bnei Yehuda": "בני יהודה",
    "Hapoel Kfar Saba": "הפועל כפר סבא",
    "Hapoel Ramat Gan": "הפועל רמת גן",
    "Hapoel Rishon LeZion": "הפועל ראשון לציון",
    "Hapoel Afula": "הפועל עפולה",
    "Hapoel Umm al-Fahm": "הפועל אום אל-פחם",
    "Maccabi Jaffa": "מכבי יפו",
    "Ironi Tiberias": "עירוני טבריה",
    "Maccabi Herzliya": "מכבי הרצליה",
    "Sektzia Nes Tziona": "סקציית נס ציונה",
    "Hapoel Nof HaGalil": "הפועל נוף הגליל",

    "Real Madrid": "ריאל מדריד",
    "Barcelona": "ברצלונה",
    "Atletico Madrid": "אתלטיקו מדריד",
    "Atlético Madrid": "אתלטיקו מדריד",
    "Sevilla": "סביליה",
    "Villarreal": "ויאריאל",
    "Real Sociedad": "ריאל סוסיאדד",
    "Girona": "ג'ירונה",
    "Real Betis": "ריאל בטיס",
    "Athletic Club": "אתלטיק בילבאו",
    "Valencia": "ולנסיה",
    "Getafe": "חטאפה",

    "Arsenal": "ארסנל",
    "Manchester City": "מנצ'סטר סיטי",
    "Manchester United": "מנצ'סטר יונייטד",
    "Liverpool": "ליברפול",
    "Chelsea": "צ'לסי",
    "Tottenham": "טוטנהאם",
    "Tottenham Hotspur": "טוטנהאם",
    "Aston Villa": "אסטון וילה",
    "Newcastle": "ניוקאסל",
    "Newcastle United": "ניוקאסל",
    "West Ham": "ווסטהאם",
    "West Ham United": "ווסטהאם",
    "Everton": "אברטון",
    "Brighton": "ברייטון",
    "Crystal Palace": "קריסטל פאלאס",
    "Wolverhampton Wanderers": "וולבס",
    "Wolves": "וולבס",
    "Nottingham Forest": "נוטינגהאם פורסט",
    "Leicester": "לסטר",

    "Israel": "ישראל",
    "France": "צרפת",
    "Italy": "איטליה",
    "Belgium": "בלגיה",
    "Spain": "ספרד",
    "England": "אנגליה",
    "Germany": "גרמניה",
    "Portugal": "פורטוגל",
    "Netherlands": "הולנד",
    "Croatia": "קרואטיה",
    "Brazil": "ברזיל",
    "Argentina": "ארגנטינה"
}


# ==================================================
# TRANSLATION
# ==================================================

def translate_team(name):

    name = (name or "").strip()

    if name in TRANSLATIONS:
        return TRANSLATIONS[name]

    cleaned = re.sub(
        r"\b(FC|F\.C\.|CF|C\.F\.|AFC|Club)\b",
        "",
        name,
        flags=re.I
    )

    cleaned = re.sub(r"\s+", " ", cleaned).strip(" -")

    return TRANSLATIONS.get(cleaned, cleaned or name)


# ==================================================
# DATABASE
# ==================================================

def get_db():

    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row

    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA journal_mode=WAL")

    return conn


def now_local():
    return datetime.now(TZ)


def now_iso():
    return now_local().isoformat(timespec="seconds")


def init_db():

    with get_db() as conn:

        columns = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(games)")
        }

        if columns and "fixture_id" not in columns:

            bets_exists = conn.execute("""
                SELECT 1
                FROM sqlite_master
                WHERE type='table' AND name='bets'
            """).fetchone()

            if bets_exists:
                conn.execute(
                    "ALTER TABLE bets RENAME TO bets_legacy"
                )

            conn.execute(
                "ALTER TABLE games RENAME TO games_legacy"
            )

        conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            name TEXT PRIMARY KEY COLLATE NOCASE,
            balance REAL NOT NULL DEFAULT 1000
                CHECK(balance >= 0),
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
            guess TEXT NOT NULL
                CHECK(guess IN ('1','X','2')),
            amount REAL NOT NULL CHECK(amount > 0),
            odds_at_bet REAL NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            payout REAL NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            UNIQUE(user_name, fixture_id),
            FOREIGN KEY(user_name) REFERENCES users(name),
            FOREIGN KEY(fixture_id) REFERENCES games(fixture_id)
        );

        CREATE INDEX IF NOT EXISTS idx_bets_user
        ON bets(user_name);

        CREATE INDEX IF NOT EXISTS idx_games_status
        ON games(status);
        """)

        # Support an older users table.
        user_columns = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(users)")
        }

        if "created_at" not in user_columns:
            conn.execute(
                "ALTER TABLE users ADD COLUMN created_at TEXT"
            )
            conn.execute(
                "UPDATE users SET created_at=? WHERE created_at IS NULL",
                (now_iso(),)
            )

        conn.commit()


# ==================================================
# API CONNECTION
# ==================================================

def api_get(path, params):

    response = requests.get(
        API_URL + path,
        headers={
            "x-apisports-key": API_KEY
        },
        params=params,
        timeout=25
    )

    response.raise_for_status()

    data = response.json()

    if data.get("errors"):
        raise RuntimeError(str(data["errors"]))

    return data.get("response", [])


# ==================================================
# REAL ODDS
# ==================================================

def get_real_odds(fixture_id):

    try:

        data = api_get(
            "/odds",
            {
                "fixture": fixture_id,
                "bet": 1
            }
        )

        for item in data:

            for bookmaker in item.get("bookmakers", []):

                for market in bookmaker.get("bets", []):

                    if (
                        market.get("id") != 1
                        and market.get("name", "").lower()
                        != "match winner"
                    ):
                        continue

                    values = {}

                    for entry in market.get("values", []):

                        label = str(
                            entry.get("value", "")
                        ).strip().lower()

                        try:
                            odd = float(entry.get("odd"))
                        except (TypeError, ValueError):
                            continue

                        if odd <= 1:
                            continue

                        if label in ("home", "1"):
                            values["1"] = odd

                        elif label in ("draw", "x"):
                            values["X"] = odd

                        elif label in ("away", "2"):
                            values["2"] = odd

                    if all(
                        key in values
                        for key in ("1", "X", "2")
                    ):

                        return (
                            values["1"],
                            values["X"],
                            values["2"],
                            True
                        )

    except Exception as e:

        app.logger.error(
            "Odds error for fixture %s: %s",
            fixture_id,
            e
        )

    return 9.99, 9.99, 9.99, False


# ==================================================
# FETCH REAL FIXTURES
# ==================================================

def fetch_live_games(days=7):

    fixtures = {}
    today = now_local().date()

    errors = []

    for offset in range(days):

        date_text = (
            today + timedelta(days=offset)
        ).isoformat()

        try:

            results = api_get(
                "/fixtures",
                {
                    "date": date_text,
                    "timezone": "Asia/Jerusalem"
                }
            )

            for item in results:

                league_id = item.get(
                    "league", {}
                ).get("id")

                fixture_id = item.get(
                    "fixture", {}
                ).get("id")

                status = item.get(
                    "fixture", {}
                ).get("status", {}).get("short")

                if (
                    league_id in ALLOWED_LEAGUES
                    and fixture_id
                    and status == "NS"
                ):

                    fixtures[fixture_id] = item

        except Exception as e:

            errors.append(str(e))

            app.logger.error(
                "Fixture API error: %s", e
            )

    if not fixtures:

        message = (
            "לא נמצאו משחקים עתידיים בליגות המאושרות."
        )

        if errors:
            message += " שגיאת API: " + errors[0][:250]

        return 0, message

    count = 0

    with get_db() as conn:

        for fixture_id, item in fixtures.items():

            league = item["league"]
            home = item["teams"]["home"]
            away = item["teams"]["away"]
            fixture = item["fixture"]

            if league["id"] not in ALLOWED_LEAGUES:
                continue

            raw_date = fixture.get("date")

            try:

                dt = datetime.fromisoformat(
                    raw_date.replace("Z", "+00:00")
                )

                kickoff_local = dt.astimezone(TZ).strftime(
                    "%d/%m/%Y %H:%M"
                )

            except Exception:

                kickoff_local = ""

            o1, ox, o2, real = get_real_odds(fixture_id)

            conn.execute("""
                INSERT INTO games (
                    fixture_id,
                    league_id,
                    league_name,
                    season,
                    home_name,
                    away_name,
                    home_logo,
                    away_logo,
                    kickoff_utc,
                    kickoff_local,
                    odd_1,
                    odd_x,
                    odd_2,
                    odds_real,
                    status,
                    updated_at
                )
                VALUES (
                    ?,?,?,?,?,?,?,?,?,?,?,?,?,?,
                    'open',?
                )

                ON CONFLICT(fixture_id)
                DO UPDATE SET
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
                fixture_id,
                league["id"],
                ALLOWED_LEAGUES[league["id"]],
                league.get("season"),
                translate_team(home.get("name")),
                translate_team(away.get("name")),
                home.get("logo"),
                away.get("logo"),
                raw_date,
                kickoff_local,
                o1,
                ox,
                o2,
                int(real),
                now_iso()
            ))

            count += 1

        conn.commit()

    return count, f"נטענו {count} משחקים מהליגות המאושרות."


# ==================================================
# REAL MATCH RESULTS
# ==================================================

def check_real_results():

    with get_db() as conn:

        games = conn.execute("""
            SELECT fixture_id
            FROM games
            WHERE status='open'
        """).fetchall()

    fixture_ids = [
        str(g["fixture_id"])
        for g in games
    ]

    if not fixture_ids:
        return 0, "אין משחקים פתוחים לבדיקה."

    finished = []
    errors = []

    for start in range(0, len(fixture_ids), 20):

        batch = fixture_ids[start:start + 20]

        try:

            response = api_get(
                "/fixtures",
                {
                    "ids": "-".join(batch)
                }
            )

            for item in response:

                fixture = item.get("fixture", {})
                fixture_id = fixture.get("id")

                status = fixture.get(
                    "status", {}
                ).get("short")

                if status not in ("FT", "AET", "PEN"):
                    continue

                # Regular-time score only.
                score = item.get("score", {}).get(
                    "fulltime"
                ) or {}

                home_goals = score.get("home")
                away_goals = score.get("away")

                if (
                    home_goals is None
                    or away_goals is None
                ):
                    continue

                if home_goals > away_goals:
                    result = "1"

                elif home_goals < away_goals:
                    result = "2"

                else:
                    result = "X"

                finished.append(
                    (fixture_id, result)
                )

        except Exception as e:

            errors.append(str(e))

            app.logger.error(
                "Results API error: %s", e
            )

    settled = 0

    with get_db() as conn:

        conn.execute("BEGIN IMMEDIATE")

        for fixture_id, result in finished:

            updated = conn.execute("""
                UPDATE games
                SET status='closed',
                    result=?
                WHERE fixture_id=?
                  AND status='open'
            """, (
                result,
                fixture_id
            ))

            if updated.rowcount == 0:
                continue

            bets = conn.execute("""
                SELECT *
                FROM bets
                WHERE fixture_id=?
                  AND status='pending'
            """, (
                fixture_id
            )).fetchall()

            for bet_row in bets:

                if bet_row["guess"] == result:

                    payout = round(
                        bet_row["amount"]
                        * bet_row["odds_at_bet"],
                        2
                    )

                    conn.execute("""
                        UPDATE users
                        SET balance=balance+?
                        WHERE name=?
                    """, (
                        payout,
                        bet_row["user_name"]
                    ))

                    conn.execute("""
                        UPDATE bets
                        SET status='won',
                            payout=?
                        WHERE id=?
                    """, (
                        payout,
                        bet_row["id"]
                    ))

                else:

                    conn.execute("""
                        UPDATE bets
                        SET status='lost',
                            payout=0
                        WHERE id=?
                    """, (
                        bet_row["id"]
                    ))

            settled += 1

        conn.commit()

    if settled:

        return (
            settled,
            f"עודכנו {settled} משחקים לפי תוצאות האמת!"
        )

    message = (
        "עדיין אין משחקים שהסתיימו עם תוצאה סופית זמינה."
    )

    if errors:
        message += " שגיאת API: " + errors[0][:200]

    return 0, message


# ==================================================
# USER HELPERS
# ==================================================

def current_user():
    return session.get("user")


def require_login():

    if not current_user():
        return redirect(url_for("index"))

    return None


def render_page(view, **kwargs):

    user = current_user()
    balance = None

    if user:

        with get_db() as conn:

            row = conn.execute(
                "SELECT balance FROM users WHERE name=?",
                (user,)
            ).fetchone()

            balance = row["balance"] if row else 0

    return render_template_string(
        PAGE,
        view=view,
        user=user,
        balance=balance,
        **kwargs
    )


# ==================================================
# HTML
# ==================================================

PAGE = r"""
<!DOCTYPE html>
<html lang="he" dir="rtl">
<head>

<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">

<title>ווינר חברים ⚽</title>

<style>

*{box-sizing:border-box}

body{
    margin:0;
    padding:12px;
    background:linear-gradient(135deg,#152744,#263f68);
    font-family:Arial,system-ui,sans-serif;
    color:white;
}

main{
    max-width:760px;
    margin:auto;
}

h1{
    text-align:center;
    margin:15px 0;
}

nav{
    display:flex;
    flex-wrap:wrap;
    gap:7px;
    justify-content:center;
    margin:12px 0;
}

nav a,.btn{
    background:#294b72;
    color:white;
    text-decoration:none;
    border:0;
    border-radius:9px;
    padding:10px 13px;
    font-weight:bold;
    cursor:pointer;
}

.card{
    background:white;
    color:#182235;
    border-radius:15px;
    padding:15px;
    margin:12px auto;
    box-shadow:0 5px 18px #0003;
}

.center{text-align:center}

input{
    padding:11px;
    border:1px solid #ccd3dc;
    border-radius:8px;
    max-width:100%;
    font-size:16px;
}

.btn-primary{
    background:#16a085;
    width:100%;
    margin-top:10px;
}

.btn-danger{
    background:#e74c3c;
}

.balance{
    text-align:center;
    font-weight:bold;
    margin:10px;
}

.match-top{
    display:flex;
    justify-content:space-between;
    gap:8px;
    align-items:center;
    color:#566;
}

.match-header{
    display:flex;
    direction:ltr;
    align-items:center;
    justify-content:space-between;
    gap:5px;
    margin:16px 0;
}

.team{
    display:flex;
    align-items:center;
    gap:6px;
    flex:1;
    min-width:0;
}

.team.home{
    justify-content:flex-start;
    text-align:left;
}

.team.away{
    justify-content:flex-end;
    text-align:right;
}

.team img{
    width:38px;
    height:38px;
    object-fit:contain;
    flex-shrink:0;
}

.team b{
    font-size:14px;
    overflow-wrap:anywhere;
}

.vs{
    font-weight:bold;
    color:#e74c3c;
}

.odds{
    display:flex;
    gap:7px;
    justify-content:space-between;
    margin:12px 0;
}

.odds label{
    flex:1;
    border:1px solid #d8dee8;
    border-radius:9px;
    padding:9px 3px;
    text-align:center;
    font-weight:bold;
}

.fallback{
    background:#fff0d5;
    color:#8a5200;
    border-radius:8px;
    padding:8px;
    font-size:13px;
    text-align:center;
}

.notice{
    padding:11px;
    border-radius:9px;
    background:#e8f6f3;
    color:#12614f;
    margin:10px 0;
}

.error{
    background:#fdecea;
    color:#922b21;
}

.status-won{
    color:#14845f;
    font-weight:bold;
}

.status-lost{
    color:#c0392b;
    font-weight:bold;
}

.status-pending{
    color:#a66b00;
    font-weight:bold;
}

table{
    width:100%;
    border-collapse:collapse;
    color:#182235;
}

td,th{
    padding:10px 5px;
    border-bottom:1px solid #e5e9ef;
    text-align:center;
}

@media(max-width:420px){

    body{padding:9px}
    .card{padding:12px}
    .team img{width:31px;height:31px}
    .team b{font-size:12px}
    .odds label{font-size:13px}

}

</style>
</head>

<body>
<main>

<h1>ווינר חברים ⚽</h1>

{% with messages=get_flashed_messages(with_categories=true) %}
{% for category,message in messages %}

<div class="card notice {{ 'error' if category=='error' else '' }}">
{{ message }}
</div>

{% endfor %}
{% endwith %}

{% if not user %}

<div class="card center">

<h2>כניסה למשחק</h2>
<p>בחר שם משתמש. אין צורך בסיסמה.</p>

<form method="post" action="{{ url_for('login') }}">

<input
name="username"
maxlength="24"
minlength="2"
placeholder="שם משתמש"
required
>

<button class="btn btn-primary" type="submit">
כניסה
</button>

</form>
</div>

{% else %}

<nav>

<a href="{{ url_for('index') }}">משחקים</a>
<a href="{{ url_for('league') }}">טבלת חברים</a>
<a href="{{ url_for('history') }}">ההימורים שלי</a>
<a href="{{ url_for('admin') }}">ניהול</a>
<a href="{{ url_for('logout') }}">יציאה</a>

</nav>

<div class="balance">
שלום {{ user }} · יתרה: {{ '%.2f'|format(balance) }} ₪
</div>


{% if view=='games' %}

{% if games %}

{% for g in games %}

<div class="card">

<div class="match-top">
<small>{{ g['league_name'] }}</small>
<small>{{ g['kickoff_local'] or 'מועד לא ידוע' }}</small>
</div>

<div class="match-header">

<div class="team home">
<img src="{{ g['home_logo'] or '' }}" alt="">
<b>{{ g['home_name'] }}</b>
</div>

<div class="vs">VS</div>

<div class="team away">
<b>{{ g['away_name'] }}</b>
<img src="{{ g['away_logo'] or '' }}" alt="">
</div>

</div>

{% if not g['odds_real'] %}

<div class="fallback">
⚠ אין יחס אמיתי זמין מהסוכנויות.
9.99 / 9.99 / 9.99 הוא יחס ברירת מחדל.
</div>

{% endif %}

<form method="post" action="{{ url_for('bet') }}">

<input
type="hidden"
name="fixture_id"
value="{{ g['fixture_id'] }}"
>

<div class="odds">

<label>
<input type="radio" name="guess" value="1" required>
<br>1<br>
{{ '%.2f'|format(g['odd_1']) }}
</label>

<label>
<input type="radio" name="guess" value="X">
<br>X<br>
{{ '%.2f'|format(g['odd_x']) }}
</label>

<label>
<input type="radio" name="guess" value="2">
<br>2<br>
{{ '%.2f'|format(g['odd_2']) }}
</label>

</div>

<input
type="number"
name="amount"
min="1"
max="{{ balance }}"
step="1"
placeholder="סכום ההימור בש״ח"
required
style="width:100%"
>

<button class="btn btn-primary" type="submit">
שליחת הימור
</button>

</form>
</div>

{% endfor %}

{% else %}

<div class="card center">
<h3>אין משחקים עתידיים פתוחים כרגע</h3>
<p>היכנס לניהול ועדכן משחקים.</p>
</div>

{% endif %}


{% elif view=='league' %}

<div class="card">

<h2 class="center">טבלת החברים 🏆</h2>

<table>

<tr>
<th>דירוג</th>
<th>שם</th>
<th>יתרה</th>
</tr>

{% for u in users %}

<tr>
<td>{{ loop.index }}</td>
<td>{{ u['name'] }}</td>
<td>{{ '%.2f'|format(u['balance']) }} ₪</td>
</tr>

{% endfor %}

</table>
</div>


{% elif view=='history' %}

<div class="card">

<h2>היסטוריית ההימורים שלי</h2>

{% if bets %}

<table>

<tr>
<th>משחק</th>
<th>בחירה</th>
<th>סכום</th>
<th>יחס</th>
<th>סטטוס</th>
<th>זכייה</th>
</tr>

{% for b in bets %}

<tr>

<td>
{{ b['home_name'] }} – {{ b['away_name'] }}
</td>

<td>{{ b['guess'] }}</td>

<td>{{ '%.2f'|format(b['amount']) }}</td>

<td>{{ '%.2f'|format(b['odds_at_bet']) }}</td>

<td class="status-{{ b['status'] }}">
{{ {'pending':'ממתין','won':'זכייה','lost':'הפסד'}.get(b['status'],b['status']) }}
</td>

<td>{{ '%.2f'|format(b['payout']) }} ₪</td>

</tr>

{% endfor %}

</table>

{% else %}

<p>עדיין אין הימורים.</p>

{% endif %}

</div>


{% elif view=='admin' %}

<div class="card">

<h2>ניהול מערכת ⚙️</h2>

<form method="post" action="{{ url_for('admin_update') }}">

<button class="btn btn-primary">
משיכת משחקים ויחסים מה-API
</button>

</form>

<form method="post" action="{{ url_for('admin_results') }}"
onsubmit="return confirm('לבדוק תוצאות אמת ולעדכן זכיות?');">

<button class="btn btn-primary">
בדיקת תוצאות אמת וחלוקת זכיות
</button>

</form>

<p>
המערכת בודקת תוצאות אמיתיות בלבד.
משחק שלא הסתיים נשאר בהמתנה.
</p>

</div>

{% endif %}

{% endif %}

</main>
</body>
</html>
"""


# ==================================================
# HOME PAGE
# ==================================================

@app.get("/")
def index():

    if not current_user():
        return render_page("games", games=[])

    now_utc = datetime.now(timezone.utc).isoformat()

    with get_db() as conn:

        games = conn.execute("""
            SELECT *
            FROM games
            WHERE status='open'
              AND kickoff_utc > ?
            ORDER BY kickoff_utc ASC
        """, (now_utc,)).fetchall()

    return render_page("games", games=games)


# ==================================================
# LOGIN WITHOUT PASSWORD
# ==================================================

@app.post("/login")
def login():

    username = re.sub(
        r"\s+",
        " ",
        request.form.get("username", "")
    ).strip()

    if not 2 <= len(username) <= 24:

        flash(
            "שם המשתמש חייב להכיל 2–24 תווים.",
            "error"
        )

        return redirect(url_for("index"))

    if any(ord(c) < 32 for c in username):

        flash("שם משתמש לא תקין.", "error")

        return redirect(url_for("index"))

    with get_db() as conn:

        conn.execute("""
            INSERT OR IGNORE INTO users
            (name,balance,created_at)
            VALUES (?,1000,?)
        """, (username, now_iso()))

        conn.commit()

        actual = conn.execute("""
            SELECT name
            FROM users
            WHERE name=? COLLATE NOCASE
        """, (username,)).fetchone()

    session.clear()

    session["user"] = actual["name"]

    flash("נכנסת בהצלחה!", "success")

    return redirect(url_for("index"))


@app.get("/logout")
def logout():

    session.clear()

    return redirect(url_for("index"))


# ==================================================
# BET
# ==================================================

@app.post("/bet")
def bet():

    if not current_user():
        return redirect(url_for("index"))

    try:

        fixture_id = int(
            request.form.get("fixture_id", "")
        )

        amount = float(
            request.form.get("amount", "0")
        )

    except (TypeError, ValueError):

        flash("נתוני ההימור אינם תקינים.", "error")

        return redirect(url_for("index"))

    guess = request.form.get("guess")

    if (
        guess not in ("1", "X", "2")
        or amount <= 0
        or not amount.is_integer()
    ):

        flash(
            "יש לבחור תוצאה ולהזין סכום שלם וחיובי.",
            "error"
        )

        return redirect(url_for("index"))

    with get_db() as conn:

        conn.execute("BEGIN IMMEDIATE")

        game = conn.execute("""
            SELECT *
            FROM games
            WHERE fixture_id=?
              AND status='open'
        """, (fixture_id,)).fetchone()

        user = conn.execute("""
            SELECT balance
            FROM users
            WHERE name=?
        """, (current_user(),)).fetchone()

        if not game:

            conn.rollback()

            flash("המשחק אינו פתוח להימורים.", "error")

            return redirect(url_for("index"))

        try:

            kickoff = datetime.fromisoformat(
                game["kickoff_utc"].replace("Z", "+00:00")
            )

            if kickoff <= datetime.now(timezone.utc):

                conn.rollback()

                flash(
                    "לא ניתן להמר לאחר תחילת המשחק.",
                    "error"
                )

                return redirect(url_for("index"))

        except Exception:

            conn.rollback()

            flash("מועד המשחק אינו תקין.", "error")

            return redirect(url_for("index"))

        if not user or user["balance"] < amount:

            conn.rollback()

            flash("אין יתרה מספקת.", "error")

            return redirect(url_for("index"))

        odd = {
            "1": game["odd_1"],
            "X": game["odd_x"],
            "2": game["odd_2"]
        }[guess]

        try:

            conn.execute("""
                INSERT INTO bets (
                    user_name,
                    fixture_id,
                    guess,
                    amount,
                    odds_at_bet,
                    created_at
                )
                VALUES (?,?,?,?,?,?)
            """, (
                current_user(),
                fixture_id,
                guess,
                amount,
                odd,
                now_iso()
            ))

        except sqlite3.IntegrityError:

            conn.rollback()

            flash(
                "כבר ביצעת הימור על המשחק הזה.",
                "error"
            )

            return redirect(url_for("index"))

        conn.execute("""
            UPDATE users
            SET balance=balance-?
            WHERE name=?
        """, (
            amount,
            current_user()
        ))

        conn.commit()

    flash("ההימור נשמר בהצלחה!", "success")

    return redirect(url_for("index"))


# ==================================================
# LEAGUE TABLE
# ==================================================

@app.get("/league")
def league():

    denied = require_login()

    if denied:
        return denied

    with get_db() as conn:

        users = conn.execute("""
            SELECT name,balance
            FROM users
            ORDER BY balance DESC,name ASC
        """).fetchall()

    return render_page("league", users=users)


# ==================================================
# HISTORY
# ==================================================

@app.get("/history")
def history():

    denied = require_login()

    if denied:
        return denied

    with get_db() as conn:

        bets = conn.execute("""
            SELECT
                b.*,
                g.home_name,
                g.away_name
            FROM bets b
            JOIN games g
              ON g.fixture_id=b.fixture_id
            WHERE b.user_name=?
            ORDER BY b.id DESC
        """, (current_user(),)).fetchall()

    return render_page("history", bets=bets)


# ==================================================
# ADMIN - NO PASSWORD
# ==================================================

@app.get("/admin")
def admin():

    return render_page("admin")


@app.post("/admin/update")
def admin_update():

    count, message = fetch_live_games()

    flash(
        message,
        "success" if count else "error"
    )

    return redirect(url_for("admin"))


# ==================================================
# REAL RESULTS ROUTES
# ==================================================

@app.route("/admin/results", methods=["GET", "POST"])
@app.route("/check_results", methods=["GET", "POST"])
def admin_results():

    settled, message = check_real_results()

    flash(
        message,
        "success" if settled else "error"
    )

    if request.path == "/check_results":
        return redirect(url_for("index"))

    return redirect(url_for("admin"))


# ==================================================
# HEALTH CHECK
# ==================================================

@app.get("/health")
def health():

    return {"status": "ok"}


@app.errorhandler(404)
def not_found(_):

    return "העמוד לא נמצא.", 404


# ==================================================
# START APPLICATION
# ==================================================

init_db()

if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "5000")),
        debug=False
    )
