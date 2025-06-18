import os
import requests
from datetime import datetime
import pytz
from flask import Flask

# Environment variables
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
FINNHUB_API_KEY = os.getenv("API_KEY")

app = Flask(__name__)

@app.route('/')
def home():
    return "✅ Live Market Screener is running."

@app.route('/scan')
def trigger_scan():
    run_screener()
    return "✅ Scan completed."

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
    now = datetime.now(pytz.timezone("US/Eastern"))
    hour, minute = now.hour, now.minute

    if not (9 <= hour < 16 or (hour == 9 and minute >= 30)):
        print(f"⏱ Outside regular hours ({now.strftime('%I:%M %p EST')}). Skipping.")
        return

    try:
        stock_list = get_us_stocks()
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
                send_telegram(
                    f"🔥 Live Market Alert\n"
                    f"Symbol: {symbol}\n"
                    f"Price: ${price:.2f}\n"
                    f"Change: {change:.2f}%\n"
                    f"Volume: {vol:,}\n"
                    f"Market Cap: ${mcap:.1f}M"
                )

    except Exception as e:
        print("❌ Screener error:", str(e))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
