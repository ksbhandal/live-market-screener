import os
import requests
from datetime import datetime
from flask import Flask
import pytz
import time

app = Flask(__name__)

BOT_TOKEN = os.environ.get("bot_token")
CHAT_ID = os.environ.get("chat_id")
FINNHUB_API_KEY = os.environ.get("FINNHUB_API_KEY")

HEADERS = {
    "X-Finnhub-Token": FINNHUB_API_KEY
}

PRICE_LIMIT = 5.00
GAP_PERCENT = 10
VOLUME_MIN = 1000000
REL_VOL_MIN = 2
TIMEZONE = pytz.timezone("US/Eastern")
SCAN_HOURS = range(9, 16)  # 9:00 AM to 3:59 PM EST

last_alerted = {}

def is_market_hours():
    now = datetime.now(TIMEZONE)
    return now.hour in SCAN_HOURS

def fetch_stocks():
    url = f"https://finnhub.io/api/v1/stock/symbol?exchange=US&token={FINNHUB_API_KEY}"
    res = requests.get(url)
    if res.status_code == 200:
        return [s['symbol'] for s in res.json() if s.get("type") == "Common Stock"]
    return []

def get_metrics(symbol):
    try:
        quote = requests.get(f"https://finnhub.io/api/v1/quote?symbol={symbol}", headers=HEADERS).json()
        profile = requests.get(f"https://finnhub.io/api/v1/stock/profile2?symbol={symbol}", headers=HEADERS).json()
        stats = requests.get(f"https://finnhub.io/api/v1/stock/metric?symbol={symbol}&metric=all", headers=HEADERS).json()

        return {
            "symbol": symbol,
            "current_price": quote.get("c"),
            "previous_close": quote.get("pc"),
            "market_cap": profile.get("marketCapitalization"),
            "volume": quote.get("v"),
            "rel_vol": stats.get("metric", {}).get("relativeVolume")
        }
    except:
        return None

def send_telegram_message(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    data = {"chat_id": CHAT_ID, "text": text}
    try:
        requests.post(url, data=data)
    except:
        pass

def scan_and_alert():
    if not is_market_hours():
        return

    now_str = datetime.now(TIMEZONE).strftime("%I:%M %p")
    send_telegram_message(f"📡 Live Market scan triggered @ {now_str}")
    symbols = fetch_stocks()
    found_any = False

    for symbol in symbols:
        metrics = get_metrics(symbol)
        if not metrics:
            continue

        price = metrics["current_price"]
        prev_close = metrics["previous_close"]
        cap = metrics["market_cap"]
        volume = metrics["volume"]
        rel_vol = metrics["rel_vol"]

        if not all([price, prev_close, cap, volume, rel_vol]):
            continue

        if price > PRICE_LIMIT:
            continue

        percent_change = ((price - prev_close) / prev_close) * 100 if prev_close else 0
        if percent_change < GAP_PERCENT:
            continue

        if volume < VOLUME_MIN:
            continue

        if rel_vol < REL_VOL_MIN:
            continue

        found_any = True

        change_diff = " 📈" if percent_change > 0 else " 📉"
        msg = (
            f"🔥 ${symbol} ALERT @ {now_str}\n"
            f"Price: ${price:.2f} | Prev Close: ${prev_close:.2f}\n"
            f"Change: {percent_change:.1f}%{change_diff}\n"
            f"Volume: {volume:,} | Rel Vol: {rel_vol:.2f}\n"
            f"Market Cap: ${cap:.0f}M"
        )
        send_telegram_message(msg)

    if not found_any:
        send_telegram_message("❌ No stocks matched criteria in this scan.")

@app.route("/")
def home():
    return "Live market scanner running."

@app.route("/scan")
def scan():
    scan_and_alert()
    return "Scan complete."

if __name__ == '__main__':
    from threading import Thread

    def ping_self():
        while True:
            try:
                requests.get("https://live-market-screener.onrender.com/scan")
            except:
                pass
            time.sleep(600)  # every 10 minutes

    Thread(target=ping_self).start()
    app.run(host="0.0.0.0", port=10000)
