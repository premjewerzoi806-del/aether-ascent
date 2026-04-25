import requests, json, time, os
from datetime import datetime
from google import genai

GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
NEWS_API_KEY = os.environ["NEWS_API_KEY"]

client = genai.Client(api_key=GEMINI_API_KEY)
CHECK_INTERVAL = 900
HISTORY_FILE = "sent_coins.json"

TOP_COINS = [
    "bitcoin", "ethereum", "solana", "binancecoin", "ripple",
    "cardano", "dogecoin", "avalanche-2", "polkadot", "matic-network",
    "chainlink", "uniswap", "litecoin", "stellar", "cosmos",
    "near", "algorand", "vechain", "tezos", "flow"
]

def load_sent():
    try:
        with open(HISTORY_FILE) as f:
            return json.load(f)
    except:
        return []

def save_sent(coin_id):
    data = load_sent()
    data.append(coin_id)
    data = data[-50:]
    with open(HISTORY_FILE, "w") as f:
        json.dump(data, f)

def fetch_market(asset_id):
    url = f"https://api.coingecko.com/api/v3/coins/{asset_id}"
    params = {"localization": "false", "tickers": "false", "community_data": "false", "developer_data": "false", "sparkline": "false"}
    resp = requests.get(url, params=params)
    if resp.status_code == 200:
        d = resp.json().get("market_data", {})
        return {
            "id": asset_id,
            "name": resp.json().get("name"),
            "symbol": resp.json().get("symbol").upper(),
            "current_price": d.get("current_price", {}).get("usd"),
            "high_24h": d.get("high_24h", {}).get("usd"),
            "low_24h": d.get("low_24h", {}).get("usd"),
            "price_change_24h": d.get("price_change_percentage_24h"),
            "total_volume": d.get("total_volume", {}).get("usd")
        }
    return None

def fetch_ohlcv(asset_id):
    url = f"https://api.coingecko.com/api/v3/coins/{asset_id}/ohlc"
    resp = requests.get(url, params={"vs_currency": "usd", "days": 3})
    if resp.status_code == 200:
        return [c[4] for c in resp.json()]
    return []

def calc_rsi(prices, period=14):
    if len(prices) < period + 1:
        return None
    g, l = [], []
    for i in range(1, len(prices)):
        d = prices[i] - prices[i-1]
        g.append(d if d > 0 else 0)
        l.append(abs(d) if d < 0 else 0)
    ag = sum(g[-period:]) / period
    al = sum(l[-period:]) / period
    if al == 0:
        return 100
    return round(100 - (100 / (1 + ag/al)), 2)

def fetch_news(asset_name):
    try:
        url = "https://newsapi.org/v2/everything"
        params = {"q": f"{asset_name} crypto", "apiKey": NEWS_API_KEY, "pageSize": 3, "sortBy": "publishedAt", "language": "en"}
        resp = requests.get(url, params=params)
        if resp.status_code == 200:
            return [a["title"] for a in resp.json().get("articles", [])[:3]]
        return []
    except:
        return []

def get_ai_signal(asset, rsi, news):
    news_text = "\n".join([f"- {n}" for n in news]) if news else "No major news"
    prompt = f"""You are a strict crypto trading AI. Output ONLY valid JSON.

Signal only if probability is 65%+. Use RSI + news sentiment.

Asset: {asset['name']} ({asset['symbol']})
Price: ${asset['current_price']}
RSI: {rsi}
24h Change: {asset['price_change_24h']:.2f}%
Volume: ${asset['total_volume']}
News:
{news_text}

Rules:
RSI < 35 + positive news = BUY
RSI > 65 + negative news = SELL
RSI 35-65 or mixed signals = NO TRADE

Output:
{{"action":"BUY/Sell/No Trade","confidence":72,"reasoning":"short reason","entry":42000,"tp":43000,"sl":41500}}"""
    try:
        resp = client.models.generate_content(model="gemini-2.0-flash", contents=prompt)
        raw = resp.text.strip().replace("```json","").replace("```","")
        return json.loads(raw)
    except:
        return None

def send_telegram(signal, asset, rsi, news_headline):
    if signal["action"] == "NO TRADE":
        return False
    news_line = f"\n📰 {news_headline}" if news_headline else ""
    msg = f"""⚡ AETHER ASCENT

📊 {asset['name']} ({asset['symbol']})
🎯 {signal['action']} | {signal['confidence']}% | RSI {rsi}

💰 Entry: ${signal['entry']:,.2f}
✅ TP: ${signal['tp']:,.2f}
🛑 SL: ${signal['sl']:,.2f}

📝 {signal['reasoning']}{news_line}

🕐 {datetime.now().strftime('%d/%m %H:%M UTC')}"""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    resp = requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": msg})
    return resp.status_code == 200

def run_scan():
    sent = load_sent()
    count = 0
    for coin_id in TOP_COINS:
        if coin_id in sent:
            continue
        market = fetch_market(coin_id)
        if not market or not market["current_price"]:
            continue
        closes = fetch_ohlcv(coin_id)
        rsi = calc_rsi(closes)
        if rsi is None:
            continue
        if rsi > 35 and rsi < 65:
            continue
        news = fetch_news(market["name"])
        signal = get_ai_signal(market, rsi, news)
        if signal and signal["action"] in ["BUY", "SELL"]:
            news_headline = news[0] if news else ""
            ok = send_telegram(signal, market, rsi, news_headline)
            save_sent(coin_id)
            tag = "OK" if ok else "FAIL"
            print(f"{tag} {market['symbol']} {signal['action']} {signal['confidence']}% RSI{rsi}")
            count += 1
            time.sleep(5)
        if count >= 3:
            break
        time.sleep(2)

print("=" * 30)
print("AETHER ASCENT LIVE")
print("=" * 30)

while True:
    now = datetime.now().strftime('%H:%M:%S')
    print(f"[{now}] Scan...")
    try:
        run_scan()
    except Exception as e:
        print(f"Err: {e}")
    print(f"Sleep {CHECK_INTERVAL}s")
    time.sleep(CHECK_INTERVAL)
