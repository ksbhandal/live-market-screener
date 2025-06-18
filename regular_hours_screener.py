import os
import requests
from datetime import datetime
import pytz
from flask import Flask
import threading
import time

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY")

app = Flask(__name__)

@app.route("/")
def home():
    return "✅ Live market screener is running."

@app.route("/scan")
def scan_route():
    send_telegram("🔄 Live Market scan triggered.")
    run_screener()
    return "✅ Scan complete."

def send_telegram(message):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message}
    try:
        res = requests.post(url, data=payload)
        print("📨 Telegram:", res.status_code, res.text)
    except Exception as e:
        print("❌ Telegram error:", str(e))

def get_us_stocks():
    url = f"https://finnhub.io/api/v1/stock/symbol?exchange=US&token={FINNHUB_API_KEY}"
    return requests.get(url).json()

def get_quote(symbol):
    url = f"https://finnhub.io/api/v1/quote?symbol={symbol}&token={FINNHUB_API_KEY}"
    return requests.get(url).json()

def get_metrics(symbol):
    url = f"https://finnhub.io/api/v1/stock/metric?symbol={symbol}&metric=all&token={FINNHUB_API_KEY}"
    return requests.get(url).json()

def run_screener():
    now = datetime.now(pytz.timezone("US/Eastern"))
    print(f"⏱ Scan triggered at {now.strftime('%Y-%m-%d %I:%M:%S %p EST')}")

    if not (9 <= now.hour < 16):
        print("⏹ Outside market hours. Scan skipped.")
        return

    try:
        stock_list = get_us_stocks()
        print(f"📦 Retrieved {len(stock_list)} symbols.")
    except Exception as e:
        print("❌ API Error:", str(e))
        send_telegram("❌ ERROR: Could not fetch stock list.")
        return

    matches = 0

    for stock in stock_list:
        symbol = stock.get("symbol", "")
        if "." in symbol:
            continue

        try:
            quote = get_quote(symbol)
            metric = get_metrics(symbol)

            price = quote.get("c")
            o_price = quote.get("o")
            volume = quote.get("v")
            rel_vol = metric.get("metric", {}).get("relativeVolume", 0)
            mcap = metric.get("metric", {}).get("marketCapitalization", 0)

            if not all([price, o_price, volume]):
                print(f"⚠️ Skipped {symbol}: Missing quote/volume.")
                continue

            change = ((price - o_price) / o_price) * 100 if o_price > 0 else 0

            if (
                price < 5 and
                change > 10 and
                volume > 1_000_000 and
                rel_vol > 2 and
                mcap < 300
            ):
                print(f"🚀 {symbol} | ${price:.2f} | {change:.2f}% | Vol: {volume:,}")
                send_telegram(
                    f"📈 Live Market Alert\n"
                    f"Symbol: {symbol}\n"
                    f"Price: ${price:.2f}\n"
                    f"% Gain: {change:.2f}%\n"
                    f"Volume: {volume:,}\n"
                    f"Rel Volume: {rel_vol:.2f}\n"
                    f"Market Cap: ${mcap:.1f}M"
                )
                matches += 1

        except Exception as e:
            print(f"❌ Error for {symbol}: {e}")

    if matches == 0:
        send_telegram("🕵️‍♂️ Scan complete — no explosive stocks found.")

def self_ping():
    while True:
        try:
            time.sleep(600)  # Every 10 minutes
            url = os.getenv("RENDER_EXTERNAL_URL")
            if url:
                requests.get(f"{url}/scan")
                print("🔁 Self-pinged /scan")
        except Exception as e:
            print("❌ Self-ping failed:", e)

if __name__ == "__main__":
    threading.Thread(target=self_ping).start()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
