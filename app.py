# app.py
# Listr: SMS shopping list using Twilio + Render + Postgres
#
# Routes:
# - GET /         -> "Listr is alive."
# - GET /privacy  -> serves privacy.html
# - GET /terms    -> serves terms.html
# - GET /debug    -> shows what files/routes exist (for troubleshooting)
# - POST /sms     -> Twilio webhook

import os
from flask import Flask, request, Response, send_file
from twilio.twiml.messaging_response import MessagingResponse
import psycopg2
import psycopg2.extras

app = Flask(__name__)

# Absolute folder where this app.py lives (works on Render)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PRIVACY_PATH = os.path.join(BASE_DIR, "privacy.html")
TERMS_PATH = os.path.join(BASE_DIR, "terms.html")
SMS_PATH = os.path.join(BASE_DIR, "sms.html")


# -------------------------
# DB
# -------------------------
def get_conn():
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        raise RuntimeError("DATABASE_URL environment variable is not set in Render.")
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)
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


# -------------------------
# Web routes
# -------------------------
@app.get("/")
def health():
    return "Listr is alive."


@app.get("/privacy")
def privacy():
    return send_file(PRIVACY_PATH)


@app.get("/terms")
def terms():
    return send_file(TERMS_PATH)

@app.get("/sms-info")
def sms_info():
    return send_file(SMS_PATH)

@app.get("/debug")
def debug():
    # Shows: current folder, which files exist, and all Flask routes
    files_here = sorted(os.listdir(BASE_DIR))
    routes = sorted([str(r) for r in app.url_map.iter_rules()])
    body = (
        "DEBUG\n\n"
        f"BASE_DIR: {BASE_DIR}\n\n"
        f"privacy.html exists? {os.path.exists(PRIVACY_PATH)}\n"
        f"terms.html exists? {os.path.exists(TERMS_PATH)}\n\n"
        f"Files in BASE_DIR:\n{files_here}\n\n"
        f"Flask routes:\n{routes}\n"
    )
    return Response(body, mimetype="text/plain")


# -------------------------
# Twilio SMS webhook
# -------------------------
@app.post("/sms")
def sms():
    init_db()

    from_number = request.form.get("From", "")
    body = (request.form.get("Body") or "").strip()
    lower = body.lower()

    resp = MessagingResponse()

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
            return Response(str(resp), mimetype="text/xml")

        msg = "Your Listr:\n"
        for i, row in enumerate(rows, 1):
            msg += f"{i}) {row['body']}\n"
        msg += "\nCleared ✅"
        resp.message(msg)

        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM items WHERE phone=%s;", (from_number,))
            conn.commit()

        return Response(str(resp), mimetype="text/xml")

    # default: add item
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
