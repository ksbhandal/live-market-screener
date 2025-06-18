import os
import requests
import threading
import time
from datetime import datetime
import pytz
from flask import Flask

# Load secrets from environment
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
FINNHUB_API_KEY = os.getenv("API_KEY")
APP_URL = os.getenv("RENDER_EXTERNAL_URL")  # Provided automatically by Render

app = Flask(__name__)
PREVIOUS_SYMBOLS = set()
LAST_HOURLY_SENT = -1

@app.route('/')
def home():
    return "✅ Live Market Screener is active and pingable."

def send_telegram(msg):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    data = {"chat_id": CHAT_ID, "text": msg}
    try:
        response = requests.post(url, data=data)
        print("📨 Telegram:", response.status_code, response.text)
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
    global PREVIOUS_SYMBOLS, LAST_HOURLY_SENT
    now = datetime.now(pytz.timezone("US/Eastern"))
    current_hour = now.hour
    current_minute = now.minute

    if not (9 <= current_hour < 16 or (current_hour == 9 and current_minute >= 30)):
        print(f"⏱ Outside regular hours ({now.strftime('%I:%M %p EST')}). Skipping.")
        return

    try:
        stock_list = get_us_stocks()
        selected = []
        current_symbols = set()

        for stock in stock_list:
            symbol = stock.get("symbol", "")
            if "." in symbol:
                continue

            quote = get_quote(symbol)
            metric = get_metrics(symbol)
            price = quote.get("c")
            pc = quote.get("pc")
            vol = quote.get("v")
            mcap = metric.get("metric", {}).get("marketCapitalization", 0)

            if not all([price, pc, vol]):
                continue

            change = ((price - pc) / pc) * 100 if pc > 0 else 0

            if price < 5 and change > 10 and vol > 1_000_000 and mcap < 300:
                current_symbols.add(symbol)
                selected.append((symbol, price, change, vol, mcap))

                if symbol not in PREVIOUS_SYMBOLS:
                    send_telegram(
                        f"🔥 Live Market Alert\n"
                        f"Symbol: {symbol}\n"
                        f"Price: ${price:.2f}\n"
                        f"Change: {change:.2f}%\n"
                        f"Volume: {vol:,}\n"
                        f"Market Cap: ${mcap:.1f}M"
                    )

        # Hourly summary
        if current_minute < 10 and current_hour != LAST_HOURLY_SENT:
            if selected:
                summary = "\n\n".join(
                    f"{s[0]}: ${s[1]:.2f} | {s[2]:.1f}% | Vol: {s[3]:,} | MC: ${s[4]:.1f}M"
                    for s in selected
                )
                send_telegram(f"📊 Hourly Summary ({now.strftime('%I:%M %p')} EST):\n\n{summary}")
            else:
                send_telegram(f"📊 Hourly Summary ({now.strftime('%I:%M %p')} EST): No matches.")

            LAST_HOURLY_SENT = current_hour

        PREVIOUS_SYMBOLS = current_symbols

    except Exception as e:
        print("❌ Screener error:", str(e))

def background_loop():
    while True:
        run_screener()
        time.sleep(600)  # every 10 minutes

def ping_self_loop():
    while True:
        try:
            if APP_URL:
                print("🔁 Pinging self to stay alive...")
                requests.get(APP_URL)
        except Exception as e:
            print("❌ Ping self failed:", str(e))
        time.sleep(840)  # every 14 minutes

# Start both background threads
threading.Thread(target=background_loop, daemon=True).start()
threading.Thread(target=ping_self_loop, daemon=True).start()

# Start the web server
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
