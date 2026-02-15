import os
import re
from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
import psycopg2
import psycopg2.extras

app = Flask(__name__)

HELP_TEXT = (
    "Listr commands:\n"
    "- text anything to add it\n"
    "- list\n"
    "- del N\n"
    "- clear\n"
    "- help"
)

def get_conn():
    db_url = os.environ.get("DATABASE_URL")
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)
    return psycopg2.connect(db_url, sslmode="require")

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

@app.get("/")
def health():
    return "Listr is alive."

@app.post("/sms")
def sms():
    init_db()

    from_number = request.form.get("From")
    body = request.form.get("Body").strip()
    lower = body.lower()

    resp = MessagingResponse()

    if lower == "help":
        resp.message(HELP_TEXT)
        return str(resp)

    if lower == "list":
        with get_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                cur.execute("SELECT id, body FROM items WHERE phone=%s ORDER BY id;", (from_number,))
                rows = cur.fetchall()

        if not rows:
            resp.message("Your Listr is empty.")
            return str(resp)

        msg = "Your Listr:\n"
        for i, row in enumerate(rows, 1):
            msg += f"{i}) {row['body']}\n"

        resp.message(msg)
        return str(resp)

    if lower == "clear":
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM items WHERE phone=%s;", (from_number,))
            conn.commit()

        resp.message("Cleared ✅")
        return str(resp)

    m = re.match(r"(del|delete)\s+(\d+)", lower)
    if m:
        n = int(m.group(2))

        with get_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                cur.execute("SELECT id, body FROM items WHERE phone=%s ORDER BY id;", (from_number,))
                rows = cur.fetchall()

            if n > len(rows):
                resp.message("Invalid item number.")
                return str(resp)

            target = rows[n-1]
            with conn.cursor() as cur2:
                cur2.execute("DELETE FROM items WHERE id=%s;", (target["id"],))
            conn.commit()

        resp.message(f"Deleted: {target['body']}")
        return str(resp)

    # default: add item
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO items (phone, body) VALUES (%s, %s);", (from_number, body))
        conn.commit()

    resp.message(f"Added: {body}")
    return str(resp)
