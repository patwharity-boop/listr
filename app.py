# app.py
# Listr: SMS list app using Twilio + Render + Postgres
# Behavior:
# - Any text (except "send") adds an item to the sender's list
# - "send" replies with the full list, then clears it

import os
from flask import Flask, request, Response, send_file
from twilio.twiml.messaging_response import MessagingResponse
import psycopg2
import psycopg2.extras

app = Flask(__name__)

# -----------------------------
# Database connection helper
# -----------------------------
def get_conn():
    # Render provides DATABASE_URL as an env var (you added it in Render)
    db_url = os.environ.get("DATABASE_URL", "")

    # Safety check so the app fails with a clear error instead of crashing weirdly
    if not db_url:
        raise RuntimeError("DATABASE_URL environment variable is not set in Render.")

    # Some providers use postgres:// but psycopg expects postgresql://
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)

    return psycopg2.connect(db_url, sslmode="require")


# -----------------------------
# Create table if it doesn't exist
# (called on-demand; fine for learning / small use)
# -----------------------------
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


# -----------------------------
# Health check endpoint
# (lets you verify the service is up)
# -----------------------------
@app.get("/")
def health():
    return "Listr is alive."


# -----------------------------
# Twilio webhook endpoint
# Twilio POSTs here when an SMS arrives
# -----------------------------
@app.post("/sms")
def sms():
    init_db()

    from_number = request.form.get("From", "")
    body = (request.form.get("Body") or "").strip()
    lower = body.lower()

    resp = MessagingResponse()

    # If they text "send", reply with the list then clear it.
    if lower == "send":
        with get_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                cur.execute(
                    "SELECT id, body FROM items WHERE phone=%s ORDER BY id;",
                    (from_number,),
                )
                rows = cur.fetchall()

            # Build reply message
            if not rows:
                resp.message("Your Listr is empty.")
            else:
                msg = "Your Listr:\n"
                for i, row in enumerate(rows, 1):
                    msg += f"{i}) {row['body']}\n"
                msg += "\nCleared ✅"
                resp.message(msg)

            # Clear after sending
            with conn.cursor() as cur2:
                cur2.execute("DELETE FROM items WHERE phone=%s;", (from_number,))
            conn.commit()

        # IMPORTANT: return TwiML as XML
        return Response(str(resp), mimetype="application/xml")

    # Otherwise: add the item
    if body:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO items (phone, body) VALUES (%s, %s);",
                    (from_number, body),
                )
            conn.commit()

        resp.message(f"Added: {body} ✅ (Text 'send' when ready)")
    else:
        resp.message("Text an item to add it, or text 'send' to receive your list.")

    # IMPORTANT: return TwiML as XML
    return Response(str(resp), mimetype="application/xml")


# -----------------------------
# Local dev only (Render uses gunicorn, not this)
# -----------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
