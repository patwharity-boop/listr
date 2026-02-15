import os
from flask import Flask, request, Response
from twilio.twiml.messaging_response import MessagingResponse
import psycopg2

app = Flask(__name__)

# -----------------------------------------
# DATABASE CONNECTION
# -----------------------------------------
def get_conn():
    # Render provides DATABASE_URL via Environment Variables
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        raise RuntimeError("DATABASE_URL environment variable is not set.")

    # Some platforms still use postgres:// but psycopg expects postgresql://
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)

    # Render Postgres commonly requires SSL
    return psycopg2.connect(db_url, sslmode="require")


# -----------------------------------------
# DATABASE INIT (creates table if missing)
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
# HEALTH CHECK (Render uses this sometimes)
# -----------------------------------------
@app.get("/")
def health():
    return "Listr is alive."


# -----------------------------------------
# TWILIO WEBHOOK ENDPOINT
# Twilio POSTs incoming SMS here
# -----------------------------------------
@app.post("/sms")
def sms():
    init_db()

    from_number = request.form.get("From", "").strip()
    body = request.form.get("Body", "").strip()

    resp = MessagingResponse()

    # Safety check
    if not from_number:
        resp.message("Missing From number.")
        return Response(str(resp), mimetype="application/xml")

    # If message body is empty
    if not body:
        resp.message("Text something to add it to your list. Text 'send' to receive the list.")
        return Response(str(resp), mimetype="application/xml")

    lower = body.lower()

    # -----------------------------------------
    # COMMAND: SEND
    # Replies with the list, then clears it
    # -----------------------------------------
    if lower == "send":
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT body FROM items WHERE phone=%s ORDER BY id;",
                    (from_number,)
                )
                rows = cur.fetchall()

            if not rows:
                resp.message("Your list is empty. Text an item like 'eggs' to add it.")
                return Response(str(resp), mimetype="application/xml")

            # Build list message
            msg_lines = ["Your Listr:"]
            for i, (item_body,) in enumerate(rows, 1):
                msg_lines.append(f"{i}) {item_body}")

            # Clear after sending
            with conn.cursor() as cur2:
                cur2.execute("DELETE FROM items WHERE phone=%s;", (from_number,))
            conn.commit()

        resp.message("\n".join(msg_lines) + "\n\nCleared ✅")
        return Response(str(resp), mimetype="application/xml")

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
    return Response(str(resp), mimetype="application/xml")
