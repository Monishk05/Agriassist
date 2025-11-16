# main.py
import os
from dotenv import load_dotenv
from datetime import datetime, timedelta, timezone
import logging

# Hide ngrok warnings
logging.getLogger("pyngrok").setLevel(logging.ERROR)

# Load .env
load_dotenv()

# === IMPORTS ===
from openai import OpenAI
openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
if not os.getenv("OPENAI_API_KEY"):
    raise ValueError("OPENAI_API_KEY not found in .env!")

import base64
import json
import sqlite3
import requests
from fastapi import FastAPI, Form
from fastapi.responses import PlainTextResponse
from fastapi.staticfiles import StaticFiles
from twilio.twiml.messaging_response import MessagingResponse
from twilio.rest import Client
from pyngrok import ngrok
import uvicorn

from utils import get_structured_prompt, text_to_speech, PUBLIC_AUDIO_DIR

# === APP ===
app = FastAPI()
app.mount("/audio", StaticFiles(directory=PUBLIC_AUDIO_DIR), name="audio")

# === TWILIO ===
twilio_client = Client(os.getenv("TWILIO_ACCOUNT_SID"), os.getenv("TWILIO_AUTH_TOKEN"))
TWILIO_WHATSAPP = os.getenv("TWILIO_WHATSAPP_NUMBER")

# === DB ===
DB_PATH = "agriassist.db"
conn = sqlite3.connect(DB_PATH, check_same_thread=False)
c = conn.cursor()
c.execute("""CREATE TABLE IF NOT EXISTS cases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    phone TEXT,
    timestamp TEXT,
    image_b64 TEXT,
    diagnosis_json TEXT,
    escalated INTEGER
)""")
c.execute("""CREATE TABLE IF NOT EXISTS rate_limit (
    phone TEXT PRIMARY KEY,
    last_image TEXT
)""")
conn.commit()

# === LANGUAGE ===
TN_AREA_CODES = {"41", "44", "45", "46", "47", "48", "49"}

def detect_language(phone: str, body: str) -> str:
    body_low = body.lower()
    if any(k in body_low for k in ["tamil", "தமிழ்", "ta"]): return "ta"
    if any(k in body_low for k in ["hindi", "हिंदी", "hi"]): return "hi"
    if phone.startswith("whatsapp:+91"):
        code = phone.split(":")[1][:4]
        if code[2:] in TN_AREA_CODES: return "ta"
    return "hi"

# === RATE LIMIT ===
RATE_LIMIT_MINUTES = 2

def can_send_image(phone: str) -> bool:
    # === NORMALIZE PHONE NUMBER ===
    phone = phone.strip()
    if not phone.startswith("whatsapp:"):
        phone = f"whatsapp:{phone}"

    now = datetime.now(timezone.utc)
    c.execute("SELECT last_image FROM rate_limit WHERE phone = ?", (phone,))
    row = c.fetchone()
    if row:
        last_str = row[0]
        try:
            last = datetime.fromisoformat(last_str)
            if last.tzinfo is None:
                last = last.replace(tzinfo=timezone.utc)
        except Exception as e:
            print(f"Rate limit parse error: {e}")
            last = now
        if now - last < timedelta(minutes=RATE_LIMIT_MINUTES):
            return False

    # === SAVE WITH FULL whatsapp: PREFIX ===
    c.execute(
        "INSERT INTO rate_limit VALUES (?, ?) ON CONFLICT(phone) DO UPDATE SET last_image = ?",
        (phone, now.isoformat(), now.isoformat())
    )
    conn.commit()
    return True

# === DOWNLOAD IMAGE ===
def download_image(media_url: str) -> str | None:
    try:
        auth = (os.getenv("TWILIO_ACCOUNT_SID"), os.getenv("TWILIO_AUTH_TOKEN"))
        resp = requests.get(media_url, auth=auth, timeout=12)
        resp.raise_for_status()
        if len(resp.content) < 20_000: return None
        return base64.b64encode(resp.content).decode("utf-8")
    except Exception as e:
        print(f"Image download failed: {e}")
        return None

# === AI ===
def analyze_image(base64_image: str, lang: str) -> dict:
    try:
        response = openai_client.chat.completions.create(
            model="gpt-4o",
            messages=[
                *get_structured_prompt(lang=lang),
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Analyze this crop photo. Return JSON only."},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}},
                    ],
                },
            ],
            response_format={"type": "json_object"},
            max_tokens=600,
            temperature=0.3,
        )
        content = response.choices[0].message.content
        if not content:
            return {"escalate": True, "diagnosis": "AI returned empty"}
        raw = content.strip()
        print(f"OpenAI Raw: {raw}")
        return json.loads(raw)
    except Exception as e:
        print(f"OpenAI Error: {e}")
        return {"escalate": True, "diagnosis": "AI failed"}

# === FORMAT REPLY ===
def format_reply(diag: dict, lang: str) -> str:
    if not diag or diag.get("escalate"):
        return "மன்னிக்கவும், படத்தை புரிந்து கொள்ள முடியவில்லை." if lang == "ta" else "क्षमा करें, फोटो समझ नहीं आया।"
    name = diag.get("diagnosis", "தெரியவில்லை" if lang == "ta" else "अज्ञात")
    eng = diag.get("english_name", "")
    conf = diag.get("confidence", 0)
    steps = ", ".join(diag.get("treatment_steps", ["தெரியவில்லை" if lang == "ta" else "अज्ञात"]))
    cost = diag.get("estimated_cost_inr", 0)
    return f"நோய்: {name}\nஆங்கிலம்: {eng}\nநம்பிக்கை: {conf}%\nசிகிச்சை: {steps}\nசெலவு: ₹{cost}" if lang == "ta" else f"रोग: {name}\nअंग्रेजी: {eng}\nविश्वास: {conf}%\nइलाज: {steps}\nलागत: ₹{cost}"

# === WEBHOOK ===
@app.post("/whatsapp")
async def whatsapp_webhook(MediaUrl0: str = Form(None), Body: str = Form(""), From: str = Form("")):
    phone = From.strip()
    if not phone.startswith("whatsapp:"):
        phone = f"whatsapp:{phone}"

    resp = MessagingResponse()
    msg = resp.message()
    lang = detect_language(phone, Body)

    # No image (text-only)
    if not MediaUrl0:
        msg.body("வணக்கம்! பயிர் புகைப்படம் அனுப்பவும்." if lang == "ta" else "नमस्ते! फसल का फोटो भेजें।")
        return PlainTextResponse(str(resp), media_type="text/xml")

    # Rate limit
    if not can_send_image(phone):
        msg.body("தயவு செய்து 2 நிமிடம் காத்திருக்கவும்." if lang == "ta" else "कृपया 2 मिनट प्रतीक्षा करें।")
        return PlainTextResponse(str(resp), media_type="text/xml")

    # Download image
    b64_image = download_image(MediaUrl0)
    if not b64_image:
        msg.body("படத்தை பதிவிறக்க முடியவில்லை." if lang == "ta" else "फोटो डाउनलोड नहीं हो सका।")
        return PlainTextResponse(str(resp), media_type="text/xml")

    # Analyze image
    result = analyze_image(b64_image, lang)

    # Prepare text reply
    text_reply = format_reply(result, lang)

    # Audio
    audio_url = text_to_speech(text_reply, lang, base_url=os.getenv("NGROK_BASE_URL", ""))

    # Save to DB
    c.execute(
        "INSERT INTO cases (phone, timestamp, image_b64, diagnosis_json, escalated) VALUES (?, ?, ?, ?, ?)",
        (phone, datetime.now(timezone.utc).isoformat(), b64_image,
         json.dumps(result), 1 if result.get("escalate") else 0)
    )
    conn.commit()

    # Send reply to WhatsApp
    msg.body(text_reply)
    if audio_url:
        msg.media(audio_url)

    return PlainTextResponse(str(resp), media_type="text/xml")


    # DB
    c.execute(
        "INSERT INTO cases (phone, timestamp, image_b64, diagnosis_json, escalated) VALUES (?, ?, ?, ?, ?)",
        (phone, datetime.now(timezone.utc).isoformat(), b64_image, json.dumps(result), 1 if result.get("escalate") else 0)
    )
    conn.commit()

    print(f"SENT TO {phone}:\n{text_reply}")
    if audio_url:
        print(f"AUDIO: {audio_url}")

    return PlainTextResponse(str(resp), media_type="text/xml")


# === STATUS ===
@app.post("/status_callback")
async def status_callback(MessageStatus: str = Form(...), MessageSid: str = Form(...)):
    print(f"DELIVERY: {MessageSid} → {MessageStatus}")
    return PlainTextResponse("OK")

# === START SERVER ===
def start_server():
    print("Starting ngrok tunnel...")
    try:
        tunnel = ngrok.connect(8000, "http")   # returns NgrokTunnel object
        public_url = tunnel.public_url         # get the actual URL string

        webhook = f"{public_url}/whatsapp"
        status = f"{public_url}/status_callback"
        os.environ["NGROK_BASE_URL"] = public_url  # root URL only

        print("=" * 70)
        print("AGRIASSIST IS LIVE!")
        print("WhatsApp Webhook URL (COPY THIS):")
        print(f"   {webhook}")
        print("Status URL:")
        print(f"   {status}")
        print("Send photo to your Twilio WhatsApp number")
        print("=" * 70)

        # AUTO-SET TWILIO
        print("Auto-setting Twilio webhook...")
        try:
            services = twilio_client.messaging.v1.services.list(limit=1)
            if services:
                sandbox = services[0]
                sandbox.update(inbound_request_url=webhook, status_callback=status)
                print("TWILIO WEBHOOK AUTO-SET!")
            else:
                print("No sandbox found. Set manually.")
        except Exception as e:
            print(f"Twilio auto-set failed: {e}")

        uvicorn.run(app, host="0.0.0.0", port=8000)
    except Exception as e:
        print(f"NGROK FAILED: {e}")
        print("Check internet or ngrok auth token")
        exit(1)



# === RUN ===
if __name__ == "__main__":
    start_server()