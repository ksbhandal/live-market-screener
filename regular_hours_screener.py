import os
import requests
from flask import Flask
import threading
import time
from datetime import datetime

API_KEY = os.environ.get("FINNHUB_API_KEY")
BOT_TOKEN = os.environ.get("bot_token")
CHAT_ID = os.environ.get("chat_id")

app = Flask(__name__)

PRICE_LIMIT = 5.00  # Price must be under or equal to $5
GAP_PERCENT = 10     # Change must be >= 10%
VOLUME_MIN = 1_000_000
REL_VOL_MIN = 2

HEADERS = {
    "X-Finnhub-Token": API_KEY
}

def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message}
    try:
        requests.post(url, data=payload)
    except:
        pass

def fetch_stock_symbols():
    url = f"https://finnhub.io/api/v1/stock/symbol?exchange=US&token={API_KEY}"
    try:
        res = requests.get(url)
        if res.status_code == 200:
            return [s['symbol'] for s in res.json() if s.get("type") == "Common Stock"]
    except:
        pass
    return []

def get_metrics(symbol):
    try:
        quote = requests.get(f"https://finnhub.io/api/v1/quote?symbol={symbol}", headers=HEADERS).json()
        profile = requests.get(f"https://finnhub.io/api/v1/stock/profile2?symbol={symbol}", headers=HEADERS).json()
        stats = requests.get(f"https://finnhub.io/api/v1/stock/metric?symbol={symbol}&metric=all", headers=HEADERS).json()

        return {
            "symbol": symbol,
            "price": quote.get("c"),
            "prev_close": quote.get("pc"),
            "volume": quote.get("v"),
            "rel_vol": stats.get("metric", {}).get("relativeVolume"),
            "market_cap": profile.get("marketCapitalization")
        }
    except:
        return None

def scan_stocks():
    print(f"Scanning stocks at {datetime.now()}")  # For debug
    symbols = fetch_stock_symbols()
    matching_stocks = []

    for symbol in symbols:
        data = get_metrics(symbol)
        if not data:
            continue

        price = data["price"]
        prev_close = data["prev_close"]
        volume = data["volume"]
        rel_vol = data["rel_vol"]
        cap = data["market_cap"]

        if not all([price, prev_close, volume, rel_vol, cap]):
            continue

        if price > PRICE_LIMIT:
            continue

        change_percent = ((price - prev_close) / prev_close) * 100 if prev_close else 0
        if change_percent < GAP_PERCENT:
            continue

        if volume < VOLUME_MIN or rel_vol < REL_VOL_MIN:
            continue

        matching_stocks.append({
            "symbol": symbol,
            "price": price,
            "prev_close": prev_close,
            "change": change_percent,
            "volume": volume,
            "rel_vol": rel_vol,
            "cap": cap
        })

    now_str = datetime.now().strftime("%I:%M %p EST")
    if matching_stocks:
        matching_stocks.sort(key=lambda x: x["change"], reverse=True)
        message = f"\U0001F680 Top Exploding Stocks @ {now_str} (Live Market):\n"
        for stock in matching_stocks[:10]:
            message += (f"- ${stock['symbol']}: {stock['change']:.2f}%\n"
                        f"  Price: ${stock['price']:.2f} | Prev: ${stock['prev_close']:.2f}\n"
                        f"  Vol: {stock['volume']:,} | RelVol: {stock['rel_vol']:.2f}\n\n")
        send_telegram_message(message.strip())
    else:
        send_telegram_message(f"No stocks matched the criteria as of {now_str}.")

@app.route("/")
def home():
    return "Live market scanner running..."

@app.route("/scan")
def scan():
    scan_stocks()
    return "Scan done."

@app.route('/favicon.ico')
def favicon():
    return '', 204

if __name__ == "__main__":
    def ping_self():
        while True:
            try:
                requests.get("https://live-market-screener.onrender.com/scan")
            except:
                pass
            time.sleep(600)  # every 10 minutes

    threading.Thread(target=ping_self).start()
    app.run(host="0.0.0.0", port=10000)
