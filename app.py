# =========================================
# LISTR (simple version)
# =========================================
# Goal:
# - User texts ANYTHING (ex: "eggs", "toilet paper")
# - We store it in a database list tied to THEIR phone number
# - ONLY COMMAND is: "send"
#     - If user texts "send", we reply with their list
#     - Then we clear their list so they start fresh
#
# Key pieces:
# - Twilio = receives SMS, forwards to our webhook (/sms)
# - Render = runs this Flask app on the internet
# - Postgres = stores items (so it survives restarts)
# =========================================

import os
from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
import psycopg2
import psycopg2.extras

# -----------------------------------------
# Create the Flask application
# -----------------------------------------
app = Flask(__name__)

# -----------------------------------------
# Connect to Postgres using DATABASE_URL (Render env var)
# -----------------------------------------
def get_conn():
    db_url = os.environ.get("DATABASE_URL")

    # If DATABASE_URL is missing, crash with a clear error
    if not db_url:
        raise RuntimeError("DATABASE_URL environment variable is not set")

    # Render sometimes uses postgres:// but psycopg2 expects postgresql://
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)

    return psycopg2.connect(db_url, sslmode="require")

# -----------------------------------------
# Create table if it doesn't exist yet
# -----------------------------------------
def init_db():
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS items (
                    id SERIAL PRIMARY KEY,
                    phone TEXT NOT NULL,
                    body TEXT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
            """)
        conn.commit()

# -----------------------------------------
# Browser check (optional)
# Visiting https://YOUR-RENDER-URL/ shows this text
# -----------------------------------------
@app.get("/")
def health():
    return "Listr is alive."

# -----------------------------------------
# Twilio webhook endpoint
# Twilio POSTs here when an SMS comes in
# -----------------------------------------
@app.post("/sms")
def sms():
    init_db()

    # Sender phone number (this is how we keep separate lists)
    from_number = (request.form.get("From") or "").strip()

    # Message content (the item or "send")
    body = (request.form.get("Body") or "").strip()
    lower = body.lower()

    # Build Twilio SMS response
    resp = MessagingResponse()

    # If message is blank, ask them to text something
    if not body:
        resp.message("Text an item (like 'eggs'). When ready, text 'send'.")
        return str(resp)

    # -----------------------------------------
    # ONLY COMMAND: "send"
    # Send the list back, then clear it
    # -----------------------------------------
    if lower == "send":
        with get_conn() as conn:
            # 1) Fetch all items for this phone number
            with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                cur.execute(
                    "SELECT body FROM items WHERE phone=%s ORDER BY id;",
                    (from_number,),
                )
                rows = cur.fetchall()

            # 2) If list is empty, tell them
            if not rows:
                resp.message("Your Listr is empty. Text items first, then text 'send'.")
                return str(resp)

            # 3) Build message
            msg = "Your Listr:\n"
            for i, row in enumerate(rows, 1):
                msg += f"{i}) {row['body']}\n"

            msg += "\n✅ Sent and cleared."

            # 4) Clear list
            with conn.cursor() as cur2:
                cur2.execute("DELETE FROM items WHERE phone=%s;", (from_number,))
            conn.commit()

        resp.message(msg)
        return str(resp)

    # -----------------------------------------
    # DEFAULT: Anything else is treated as an item to add
    # -----------------------------------------
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO items (phone, body) VALUES (%s, %s);",
                (from_number, body),
            )
        conn.commit()

    resp.message(f"Added: {body} ✅ (Text 'send' when ready)")
    return str(resp)
