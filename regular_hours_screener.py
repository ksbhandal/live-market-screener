import os
import requests
import pytz
from datetime import datetime
from flask import Flask
import time

app = Flask(__name__)

TELEGRAM_TOKEN = os.getenv("bot_token")
CHAT_ID = os.getenv("chat_id")
FINNHUB_API_KEY = os.getenv("finnhub_api_key")

def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {"chat_id": CHAT_ID, "text": message}
    try:
        response = requests.post(url, data=data)
        if response.status_code != 200:
            print("Telegram error:", response.text)
    except Exception as e:
        print("Telegram exception:", e)

def get_finnhub_symbols():
    url = f"https://finnhub.io/api/v1/stock/symbol?exchange=US&token={FINNHUB_API_KEY}"
    response = requests.get(url)
    return response.json() if response.status_code == 200 else []

def get_quote(symbol):
    url = f"https://finnhub.io/api/v1/quote?symbol={symbol}&token={FINNHUB_API_KEY}"
    response = requests.get(url)
    return response.json() if response.status_code == 200 else None

def get_company_profile(symbol):
    url = f"https://finnhub.io/api/v1/stock/profile2?symbol={symbol}&token={FINNHUB_API_KEY}"
    response = requests.get(url)
    return response.json() if response.status_code == 200 else None

def get_relative_volume(symbol):
    url = f"https://finnhub.io/api/v1/indicator?symbol={symbol}&resolution=15&indicator=volume&token={FINNHUB_API_KEY}"
    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        if "v" in data and len(data["v"]) >= 3:
            current_vol = data["v"][-1]
            avg_vol = sum(data["v"][-3:]) / 3
            if avg_vol == 0:
                return 0
            return current_vol / avg_vol
    return 0

@app.route('/')
def home():
    return 'Live Market Screener is running!'

@app.route('/scan')
def scan():
    # Timezone check
    eastern = pytz.timezone('US/Eastern')
    now = datetime.now(eastern)
    print(f"[{now.strftime('%Y-%m-%d %H:%M:%S')}] Checking time window for LIVE market scan...")

    if now.hour < 9 or (now.hour == 9 and now.minute < 30) or now.hour >= 16:
        print(f"[{now.strftime('%Y-%m-%d %H:%M:%S')}] ❌ Outside LIVE market window. Exiting.")
        return "Outside live market window. Scan skipped."

    print(f"[{now.strftime('%Y-%m-%d %H:%M:%S')}] ✅ Inside LIVE market window. Starting scan...")

    send_telegram_message("🔍 Live market scan triggered.")
    alerted_symbols = set()

    try:
        symbols = get_finnhub_symbols()
        print(f"🔁 Retrieved {len(symbols)} symbols.")
    except Exception as e:
        print("❌ Error fetching symbols:", e)
        return "Symbol fetch error."

    for stock in symbols:
        try:
            symbol = stock.get("symbol", "")
            if not symbol or not symbol.isalpha():
                continue

            profile = get_company_profile(symbol)
            if not profile or "marketCapitalization" not in profile:
                continue

            market_cap = profile["marketCapitalization"]
            if market_cap is None or market_cap > 300:
                continue

            quote = get_quote(symbol)
            if not quote or not quote.get("c") or not quote.get("pc"):
                continue

            current_price = quote["c"]
            prev_close = quote["pc"]
            if current_price < 0.5 or current_price > 5:
                continue

            price_change = ((current_price - prev_close) / prev_close) * 100
            if price_change < 10:
                continue

            volume = quote.get("v", 0)
            if volume < 1000000:
                continue

            rel_vol = get_relative_volume(symbol)
            if rel_vol < 2:
                continue

            if symbol not in alerted_symbols:
                alerted_symbols.add(symbol)
                message = (
                    f"🔥 ${symbol} ALERT!\n"
                    f"Price: ${current_price:.2f}\n"
                    f"Change: {price_change:.2f}%\n"
                    f"Volume: {volume:,}\n"
                    f"Rel Vol: {rel_vol:.2f}\n"
                    f"Market Cap: ${market_cap:.2f}M"
                )
                send_telegram_message(message)
                print(f"✅ Sent alert for {symbol}")

            time.sleep(0.1)

        except Exception as e:
            print(f"❌ Error processing {symbol}: {e}")

    return "Scan completed."

if __name__ == '__main__':
    app.run(debug=True)
