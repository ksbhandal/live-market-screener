import os
import time
import requests
import pytz
from datetime import datetime
from flask import Flask
from threading import Thread

app = Flask(__name__)

# === Configuration ===
API_KEY = os.getenv("FINNHUB_API_KEY")
BOT_TOKEN = os.getenv("bot_token")
CHAT_ID = os.getenv("chat_id")

# === Scanner Logic ===
def scan_and_alert():
    est = pytz.timezone('US/Eastern')
    now = datetime.now(est)

    # Run only during regular market hours (9:30 AM to 4:00 PM EST)
    market_start = now.replace(hour=9, minute=30, second=0, microsecond=0)
    market_end = now.replace(hour=16, minute=0, second=0, microsecond=0)
    if not (market_start <= now <= market_end):
        print("Outside regular market hours. Skipping scan.")
        return

    print("\n[INFO] Live market scan triggered at:", now.strftime("%Y-%m-%d %H:%M:%S"))

    url = f"https://finnhub.io/api/v1/stock/symbol?exchange=US&token={API_KEY}"
    try:
        response = requests.get(url)
        symbols = response.json()
    except Exception as e:
        print("[ERROR] Failed to fetch symbols:", e)
        return

    alerts = []
    for stock in symbols:
        try:
            symbol = stock['symbol']

            # Basic filter: penny stocks under $5
            quote_url = f"https://finnhub.io/api/v1/quote?symbol={symbol}&token={API_KEY}"
            q = requests.get(quote_url).json()

            c = q.get("c")   # current price
            pc = q.get("pc") # previous close
            v = q.get("v")   # volume

            if not all([c, pc, v]) or c > 5:
                continue

            # Filter: 20%+ gain since market open
            percent_change = ((c - pc) / pc) * 100 if pc else 0
            if percent_change < 20:
                continue

            # Filter: volume > 1M for live market
            if v < 1_000_000:
                continue

            # Filter: market cap < 300M
            profile_url = f"https://finnhub.io/api/v1/stock/profile2?symbol={symbol}&token={API_KEY}"
            p = requests.get(profile_url).json()
            market_cap = p.get("marketCapitalization", 9999)
            if market_cap > 300:
                continue

            # Relative volume (optional)
            metrics_url = f"https://finnhub.io/api/v1/stock/metric?symbol={symbol}&metric=all&token={API_KEY}"
            m = requests.get(metrics_url).json()
            rel_vol = m.get("metric", {}).get("relativeVolume", 0)
            if rel_vol < 2:
                continue

            alert_msg = f"🚀 ${symbol} up {percent_change:.1f}% | Price: ${c:.2f} | Vol: {v:,} | RelVol: {rel_vol:.2f}"
            alerts.append(alert_msg)
        except:
            continue

    if alerts:
        message = "\n".join(alerts)
    else:
        message = "🔄 Live market scan triggered."

    try:
        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            data={"chat_id": CHAT_ID, "text": message}
        )
    except Exception as e:
        print("[ERROR] Telegram failed:", e)

# === Self-pinging route for UptimeRobot ===
@app.route('/')
def home():
    return "Live Market Screener Running"

@app.route('/scan')
def manual_scan():
    scan_and_alert()
    return "Scan triggered"

# === Start Scheduled Scanning Thread ===
def schedule_loop():
    while True:
        scan_and_alert()
        time.sleep(600)  # 10 minutes

if __name__ == '__main__':
    Thread(target=schedule_loop).start()
    app.run(host="0.0.0.0", port=10000)
