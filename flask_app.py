
@app.route("/admin/results", methods=["POST"])
@app.route("/check_results", methods=["GET", "POST"])
def admin_results():

    if not API_KEY:
        flash("מפתח API חסר. לא עודכנו תוצאות.", "error")
        return redirect(url_for("admin"))

    with db() as conn:
        games = conn.execute("""
            SELECT fixture_id
            FROM games
            WHERE status='open'
        """).fetchall()

    fixture_ids = [str(g["fixture_id"]) for g in games]

    if not fixture_ids:
        flash("אין משחקים פתוחים לבדיקה.", "error")
        return redirect(url_for("admin"))

    finished_results = []
    errors = []

    # API-Football supports batches of up to 20 fixture IDs
    for start in range(0, len(fixture_ids), 20):

        batch = fixture_ids[start:start + 20]

        try:
            response = api_get(
                "/fixtures",
                {"ids": "-".join(batch)}
            )

            for item in response:

                fixture_id = item.get("fixture", {}).get("id")
                status = item.get("fixture", {}).get(
                    "status", {}
                ).get("short")

                # Only genuinely finished matches
                if status not in ("FT", "AET", "PEN"):
                    continue

                # 1X2 Match Winner is settled using
                # the regular-time fulltime score (90 minutes).
                score = item.get("score", {}).get("fulltime") or {}

                home_goals = score.get("home")
                away_goals = score.get("away")

                if home_goals is None or away_goals is None:
                    continue

                if home_goals > away_goals:
                    result = "1"
                elif home_goals < away_goals:
                    result = "2"
                else:
                    result = "X"

                finished_results.append((fixture_id, result))

        except Exception as e:
            errors.append(str(e))
            app.logger.error("Results API error: %s", e)

    settled = 0

    with db() as conn:

        conn.execute("BEGIN IMMEDIATE")

        for fixture_id, result in finished_results:

            # Do not settle a fixture twice
            updated = conn.execute("""
                UPDATE games
                SET status='closed', result=?
                WHERE fixture_id=? AND status='open'
            """, (result, fixture_id))

            if updated.rowcount == 0:
                continue

            bets = conn.execute("""
                SELECT *
                FROM bets
                WHERE fixture_id=?
                AND status='pending'
            """, (fixture_id,)).fetchall()

            for bet_row in bets:

                if bet_row["guess"] == result:

                    payout = round(
                        bet_row["amount"] *
                        bet_row["odds_at_bet"],
                        2
                    )

                    conn.execute("""
                        UPDATE users
                        SET balance = balance + ?
                        WHERE name = ?
                    """, (
                        payout,
                        bet_row["user_name"]
                    ))

                    conn.execute("""
                        UPDATE bets
                        SET status='won', payout=?
                        WHERE id=?
                    """, (
                        payout,
                        bet_row["id"]
                    ))

                else:

                    conn.execute("""
                        UPDATE bets
                        SET status='lost', payout=0
                        WHERE id=?
                    """, (bet_row["id"],))

            settled += 1

        conn.commit()

    if settled:
        flash(
            f"עודכנו {settled} משחקים לפי תוצאות האמת וחושבו הזכיות!",
            "success"
        )
    else:
        flash(
            "עדיין אין משחקים שהסתיימו עם תוצאה סופית זמינה.",
            "error"
        )

    if errors:
        app.logger.error("Some result batches failed: %s", errors)

    return redirect(url_for("admin"))
