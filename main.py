import requests, time
from datetime import datetime, timezone

TELEGRAM_TOKEN = "8232521107:AAEPmqb846XRHt7rZSsXFi-vuPcAcaz8Ogs"
CHAT_ID = "6637699767"

def send(msg):
    requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
    data={"chat_id": CHAT_ID, "text": msg}, timeout=30)

send("ALIEN PROTOCOL ONLINE — First scan running...")

while True:
    send(f"Alive at {datetime.now(timezone.utc).strftime('%H:%M UTC')}")
    time.sleep(3600)
