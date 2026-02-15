# app.py
# Listr: SMS shopping list using Twilio + Render + Postgres
#
# Behavior:
# - Any text (except "send") adds an item to the sender's list
# - "send" replies with the full list, then clears it
#
# Also serves:
# - GET /            -> health check ("Listr is alive.")
# - GET /privacy     -> serves privacy.html
# - GET /terms       -> serves terms.html

import os

from flask import Flask, request, Response, send_file
from twilio.twiml.messaging_response import MessagingResponse
import psycopg2
import psycopg2.extras

app = Flask(__name__)


# -----------------------------------------
# DATABASE: connect using Render env var DATABASE_URL
# -----------------------------------------
def get_conn():
    db_url = os.environ.get("DATABASE_URL")

    # If DATABASE_URL isn't set yet, fail loudly (helps debugging)
    if not db_url:
        raise RuntimeError("DATABASE_URL environment variable is not set in Render.")

    # Some providers use postgres:// but psycopg2 prefers postgresql://
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)

    # Render managed Postgres typically requires SSL
    return psycopg2.connect(db_url, sslmode="require")


def init_db():
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS items (
                    id SERIAL PRIMARY KEY,
                    phone TEXT NOT NULL,
                    body TEXT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                """
            )
        conn.commit()


# -----------------------------------------
# WEB PAGES: health + policy pages for Twilio
# -----------------------------------------
@app.get("/")
def health():
    return "Listr is alive."


@app.get("/privacy")
def privacy():
    # privacy.html is in the repo root (same folder as app.py)
    return send_file("privacy.html")


@app.get("/terms")
def terms():
    # terms.html is in the repo root (same folder as app.py)
    return send_file("terms.html")


# -----------------------------------------
# TWILIO WEBHOOK: incoming SMS hits POST /sms
# -----------------------------------------
@app.post("/sms")
def sms():
    init_db()

    from_number = request.form.get("From", "")
    body = (request.form.get("Body") or "").strip()
    lower = body.lower()

    resp = MessagingResponse()

    # If user texts SEND -> return list and clear it
    if lower == "send":
        with get_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                cur.execute(
                    "SELECT body FROM items WHERE phone=%s ORDER BY id;",
                    (from_number,),
                )
                rows = cur.fetchall()

        if not rows:
            resp.message("Your Listr is empty. Text items like 'eggs' to add them.")
        else:
            msg = "Your Listr:\n"
            for i, row in enumerate(rows, 1):
                msg += f"{i}) {row['body']}\n"
            msg += "\nCleared ✅"
            resp.message(msg)

            # Clear after sending
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM items WHERE phone=%s;", (from_number,))
                conn.commit()

        # IMPORTANT: Twilio expects XML, so return as text/xml
        return Response(str(resp), mimetype="text/xml")

    # Otherwise: treat message as an item to add
    if not body:
        resp.message("Text an item (like 'eggs'). Text SEND when you're ready.")
        return Response(str(resp), mimetype="text/xml")

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO items (phone, body) VALUES (%s, %s);",
                (from_number, body),
            )
        conn.commit()

    resp.message(f"Added: {body} ✅ (Text SEND when ready)")
    return Response(str(resp), mimetype="text/xml")
