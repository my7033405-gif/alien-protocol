import requests
import csv
import os
import json
import time
import re
import threading
from datetime import datetime, timezone

# ── CONFIG ──────────────────────────────────────────────
TOMORROW_API_KEY = "p2JMu0blVvwGhae9BNTX6A2acUFRoUCi"
OPENWEATHER_KEY  = "2d1986adb664b8bf755e2bb49bb5636d"
GROQ_API_KEY     = "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"
TELEGRAM_TOKEN   = "8232521107:AAEPmqb846XRHt7rZSsXFi-vuPcAcaz8Ogs"
CHAT_ID          = "6637699767"
LOG_FILE         = "signals_v7.csv"
STATS_FILE       = "stats_v7.json"
MIN_SCORE        = 55

# ── CITY TIMEZONE DATABASE ───────────────────────────────
# Each city has coords + UTC offset so bot knows local time
CITY_COORDS = {
    "london":        {"lat": 51.5074,  "lon": -0.1278},
    "tokyo":         {"lat": 35.6762,  "lon": 139.6503},
    "paris":         {"lat": 48.8566,  "lon":  2.3522},
    "toronto":       {"lat": 43.6510,  "lon": -79.3470},
    "sao paulo":     {"lat": -23.5505, "lon": -46.6333},
    "seoul":         {"lat": 37.5665,  "lon": 126.9780},
    "shanghai":      {"lat": 31.2304,  "lon": 121.4737},
    "wellington":    {"lat": -41.2866, "lon": 174.7756},
    "buenos aires":  {"lat": -34.6037, "lon": -58.3816},
    "hong kong":     {"lat": 22.3193,  "lon": 114.1694},
    "new york":      {"lat": 40.7128,  "lon": -74.0060},
    "berlin":        {"lat": 52.5200,  "lon":  13.4050},
    "madrid":        {"lat": 40.4168,  "lon": -3.7038},
    "sydney":        {"lat": -33.8688, "lon": 151.2093},
    "singapore":     {"lat":  1.3521,  "lon": 103.8198},
    "beijing":       {"lat": 39.9042,  "lon": 116.4074},
    "moscow":        {"lat": 55.7558,  "lon":  37.6173},
    "chengdu":       {"lat": 30.5728,  "lon": 104.0668},
    "warsaw":        {"lat": 52.2297,  "lon":  21.0122},
    "wuhan":         {"lat": 30.5928,  "lon": 114.3055},
    "chicago":       {"lat": 41.8781,  "lon": -87.6298},
    "los angeles":   {"lat": 34.0522,  "lon": -118.2437},
    "miami":         {"lat": 25.7617,  "lon": -80.1918},
    "seattle":       {"lat": 47.6062,  "lon": -122.3321},
    "denver":        {"lat": 39.7392,  "lon": -104.9903},
    "atlanta":       {"lat": 33.7490,  "lon": -84.3880},
    "houston":       {"lat": 29.7604,  "lon": -95.3698},
    "austin":        {"lat": 30.2672,  "lon": -97.7431},
    "san francisco": {"lat": 37.7749,  "lon": -122.4194},
    "dallas":        {"lat": 32.7767,  "lon": -96.7970},
    "mumbai":        {"lat": 19.0760,  "lon":  72.8777},
    "dubai":         {"lat": 25.2048,  "lon":  55.2708},
    "lagos":         {"lat":  6.5244,  "lon":   3.3792},
    "nairobi":       {"lat": -1.2921,  "lon":  36.8219},
    "cairo":         {"lat": 30.0444,  "lon":  31.2357},
    "istanbul":      {"lat": 41.0082,  "lon":  28.9784},
    "amsterdam":     {"lat": 52.3676,  "lon":   4.9041},
    "rome":          {"lat": 41.9028,  "lon":  12.4964},
    "barcelona":     {"lat": 41.3851,  "lon":   2.1734},
    "vienna":        {"lat": 48.2082,  "lon":  16.3738},
    "prague":        {"lat": 50.0755,  "lon":  14.4378},
    "bangkok":       {"lat": 13.7563,  "lon": 100.5018},
    "jakarta":       {"lat": -6.2088,  "lon": 106.8456},
    "manila":        {"lat": 14.5995,  "lon": 120.9842},
    "kuala lumpur":  {"lat":  3.1390,  "lon": 101.6869},
    "taipei":        {"lat": 25.0330,  "lon": 121.5654},
    "osaka":         {"lat": 34.6937,  "lon": 135.5023},
    "shenzhen":      {"lat": 22.5431,  "lon": 114.0579},
    "guangzhou":     {"lat": 23.1291,  "lon": 113.2644},
    "mexico city":   {"lat": 19.4326,  "lon": -99.1332},
    "bogota":        {"lat":  4.7110,  "lon": -74.0721},
    "lima":          {"lat": -12.0464, "lon": -77.0428},
    "santiago":      {"lat": -33.4489, "lon": -70.6693},
    "johannesburg":  {"lat": -26.2041, "lon":  28.0473},
    "montreal":      {"lat": 45.5017,  "lon": -73.5673},
    "vancouver":     {"lat": 49.2827,  "lon": -123.1207},
}

# ── STEP 1: FETCH LIVE MARKETS FROM POLYMARKET ───────────

def fetch_live_markets():
    """
    Fetches today's HIGHEST temperature markets from Polymarket.
    Returns list of {city, market_temp, probability, question, slug}
    """
    print("Fetching live markets from Polymarket...")
    today = datetime.now(timezone.utc)
    today_str = today.strftime("%-B %-d")  # "May 19"
    tomorrow_str = (today).strftime("%B %-d")

    markets_found = []

    try:
        # Fetch active markets
        url = "https://gamma-api.polymarket.com/markets?active=true&closed=false&limit=200"
        r = requests.get(url, timeout=30)
        all_markets = r.json()

        for market in all_markets:
            question = market.get("question", "")
            q_lower = question.lower()

            # Only highest temperature markets
            if "highest" not in q_lower:
                continue

            # Parse city name from question
            # Format: "Highest temperature in CITY on Month Day?"
            city_match = re.search(
                r'highest temperature in (.+?) on ([a-z]+ \d+)',
                q_lower
            )
            if not city_match:
                continue

            city_name = city_match.group(1).strip()
            market_date = city_match.group(2).strip()

            # Only today's markets
            if today_str.lower() not in market_date and tomorrow_str.lower() not in market_date:
                continue

            # Parse outcomes and prices
            try:
                outcomes = market.get("outcomes", "[]")
                prices = market.get("outcomePrices", "[]")
                if isinstance(outcomes, str):
                    outcomes = json.loads(outcomes)
                if isinstance(prices, str):
                    prices = json.loads(prices)

                for i, outcome in enumerate(outcomes):
                    temp_match = re.search(r'(-?\d+)', str(outcome))
                    if temp_match and i < len(prices):
                        temp = int(temp_match.group(1))
                        prob = round(float(prices[i]) * 100, 1)
                        if prob > 2:  # ignore dust
                            markets_found.append({
                                "city": city_name,
                                "city_display": city_name.title(),
                                "market_temp": temp,
                                "probability": prob,
                                "question": question,
                                "date": market_date,
                            })
            except Exception as e:
                continue

        print(f"Found {len(markets_found)} live market entries across {len(set(m['city'] for m in markets_found))} cities")
        return markets_found

    except Exception as e:
        print(f"Polymarket fetch error: {e}")
        return []

# ── STEP 2: GET COORDINATES FOR CITY ─────────────────────

def get_coords(city_name):
    """Match city name to coordinates database."""
    city_lower = city_name.lower().strip()

    # Direct match
    if city_lower in CITY_COORDS:
        return CITY_COORDS[city_lower]

    # Partial match
    for key in CITY_COORDS:
        if key in city_lower or city_lower in key:
            return CITY_COORDS[key]

    # Geocode via OpenWeatherMap if not in database
    try:
        url = f"https://api.openweathermap.org/geo/1.0/direct?q={city_name}&limit=1&appid={OPENWEATHER_KEY}"
        r = requests.get(url, timeout=10)
        data = r.json()
        if data:
            return {"lat": data[0]["lat"], "lon": data[0]["lon"]}
    except:
        pass

    return None

# ── STEP 3: GET REAL TEMPERATURE ─────────────────────────

def get_openmeteo(lat, lon):
    url = (
        f"https://api.open-meteo.com/v1/forecast"
        f"?latitude={lat}&longitude={lon}"
        f"&daily=temperature_2m_max&timezone=UTC&forecast_days=1"
    )
    r = requests.get(url, timeout=30)
    data = r.json()
    temps = data.get("daily", {}).get("temperature_2m_max", [])
    return round(float(temps[0]), 1) if temps else None

def get_tomorrow_io(lat, lon):
    url = (
        f"https://api.tomorrow.io/v4/weather/forecast"
        f"?location={lat},{lon}"
        f"&timesteps=1d&units=metric&apikey={TOMORROW_API_KEY}"
    )
    r = requests.get(url, timeout=30)
    data = r.json()
    try:
        today = data["timelines"]["daily"][0]["values"]
        return round(float(today["temperatureMax"]), 1)
    except:
        return None

def get_real_temp(lat, lon):
    results = {}
    try:
        t = get_openmeteo(lat, lon)
        if t: results["Open-Meteo"] = t
    except: pass
    try:
        t = get_tomorrow_io(lat, lon)
        if t: results["Tomorrow.io"] = t
    except: pass

    if not results:
        return None, "no data", "NONE"

    temps = list(results.values())
    avg = round(sum(temps) / len(temps), 1)
    sources = " + ".join(results.keys())

    if len(temps) == 1:
        conf = "SINGLE"
    else:
        spread = max(temps) - min(temps)
        if spread <= 1.0:   conf = "HIGH"
        elif spread <= 2.0: conf = "MEDIUM"
        else:               conf = "LOW"

    return avg, sources, conf

# ── STEP 4: SCORE SIGNAL ─────────────────────────────────

def confidence_score(gap, probability, hour_utc, data_conf):
    score = 0
    if gap >= 6:   score += 35
    elif gap >= 4: score += 28
    elif gap >= 3: score += 21
    elif gap >= 2: score += 14
    elif gap >= 1: score += 7
    if probability <= 10:   score += 30
    elif probability <= 20: score += 24
    elif probability <= 30: score += 18
    elif probability <= 40: score += 12
    elif probability <= 50: score += 6
    if 4 <= hour_utc <= 9:      score += 20
    elif 10 <= hour_utc <= 13:  score += 15
    elif 14 <= hour_utc <= 17:  score += 8
    else:                       score += 3
    if data_conf == "HIGH":     score += 15
    elif data_conf == "MEDIUM": score += 8
    elif data_conf == "SINGLE": score += 5
    return min(score, 100)

# ── STEP 5: GROQ AI VERDICT ──────────────────────────────

def ai_verdict(city, real_temp, market_temp, probability, gap, score, data_conf, hour_utc):
    prompt = (
        f"You are a Polymarket weather trading expert. Be brutal and short.\n\n"
        f"City: {city}\n"
        f"Market: Highest temp = {market_temp}C at {probability}% probability\n"
        f"Real temp forecast: {real_temp}C\n"
        f"Gap: {gap:+.1f}C | Score: {score}/100 | Data: {data_conf} | Hour: {hour_utc}UTC\n\n"
        f"Answer in exactly 3 lines:\n"
        f"Line 1: Should I bet YES on {market_temp}C? Why?\n"
        f"Line 2: Biggest risk?\n"
        f"Line 3: STRONG BET / BET / PASS / AVOID"
    )
    try:
        r = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": "llama3-70b-8192",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 120,
                "temperature": 0.2
            },
            timeout=30
        )
        result = r.json()
        return result["choices"][0]["message"]["content"].strip()
    except Exception as e:
        return f"AI error: {e}"

# ── BET CARD ─────────────────────────────────────────────

def build_bet_card(signal, verdict, rank):
    payout = round(1 / (signal["probability"] / 100), 2)
    return (
        f"BET #{rank} — {signal['city_display'].upper()}\n"
        f"─────────────────────\n"
        f"Date: {signal['date'].title()}\n"
        f"Market: Highest temp = {signal['market_temp']}C\n"
        f"Market says: {signal['probability']}% chance\n"
        f"Real forecast: {signal['real_temp']}C\n"
        f"Gap: {signal['gap']:+.1f}C above market\n"
        f"Score: {signal['score']}/100\n"
        f"Sources: {signal['sources']}\n"
        f"Data confidence: {signal['data_conf']}\n"
        f"Payout: ${payout} per $1 bet\n"
        f"─────────────────────\n"
        f"AI VERDICT:\n{verdict}\n"
        f"─────────────────────\n"
        f"HOW TO BET:\n"
        f"polymarket.com → Weather → Temperature\n"
        f"Search: '{signal['question']}'\n"
        f"Click YES on {signal['market_temp']}C"
    )

# ── STATS ────────────────────────────────────────────────

def load_stats():
    if os.path.exists(STATS_FILE):
        with open(STATS_FILE, "r") as f:
            return json.load(f)
    return {"wins": 0, "losses": 0, "total_bets": 0,
            "total_signals": 0, "daily_log": {}}

def save_stats(stats):
    with open(STATS_FILE, "w") as f:
        json.dump(stats, f, indent=2)

def win_rate(stats):
    total = stats["wins"] + stats["losses"]
    return round((stats["wins"] / total) * 100, 1) if total > 0 else 0

# ── TELEGRAM ─────────────────────────────────────────────

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        requests.post(url, data={"chat_id": CHAT_ID, "text": message}, timeout=30)
    except Exception as e:
        print(f"Telegram error: {e}")

def get_updates(offset=None):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
    params = {"timeout": 5}
    if offset:
        params["offset"] = offset
    try:
        r = requests.get(url, params=params, timeout=10)
        return r.json().get("result", [])
    except:
        return []

# ── MAIN SCAN ────────────────────────────────────────────

def run_scan(silent=False):
    now = datetime.now(timezone.utc)
    hour_utc = now.hour
    today_display = now.strftime("%Y-%m-%d %H:%M UTC")
    print(f"\n[{today_display}] Starting v7 scan...")

    # Step 1: Get live markets from Polymarket
    live_markets = fetch_live_markets()

    if not live_markets:
        msg = (
            f"ALIEN PROTOCOL v7\n"
            f"{today_display}\n"
            f"─────────────────────\n"
            f"No active markets found on Polymarket right now.\n"
            f"Markets usually open at midnight UTC.\n"
            f"Try again in 30 minutes."
        )
        if not silent:
            send_telegram(msg)
        return [], []

    # Step 2: For each market get real temp and score
    stats = load_stats()
    top_bets = []
    watches = []
    processed = set()

    for market in live_markets:
        city = market["city"]
        key = f"{city}_{market['market_temp']}"
        if key in processed:
            continue
        processed.add(key)

        coords = get_coords(city)
        if not coords:
            print(f"  NO COORDS {city}")
            continue

        try:
            real_temp, sources, data_conf = get_real_temp(
                coords["lat"], coords["lon"]
            )
            if real_temp is None:
                print(f"  NO TEMP   {city}")
                continue

            gap = real_temp - market["market_temp"]
            score = confidence_score(gap, market["probability"], hour_utc, data_conf)

            signal = {
                **market,
                "real_temp": real_temp,
                "gap": gap,
                "score": score,
                "sources": sources,
                "data_conf": data_conf,
            }

            tag = (
                f"[{score}] {market['city_display']}: "
                f"Real {real_temp}C vs {market['market_temp']}C "
                f"@ {market['probability']}% | Gap {gap:+.1f} [{data_conf}]"
            )

            if gap >= 2 and market["probability"] < 40 and score >= MIN_SCORE:
                top_bets.append((score, tag, signal))
                print(f"  GREEN  {tag}")
            elif gap >= 1 and market["probability"] < 50 and score >= MIN_SCORE - 10:
                watches.append((score, tag, signal))
                print(f"  WATCH  {tag}")
            else:
                print(f"  SKIP   {tag}")

            time.sleep(0.5)  # rate limit

        except Exception as e:
            print(f"  ERROR {city}: {e}")

    top_bets.sort(key=lambda x: x[0], reverse=True)
    watches.sort(key=lambda x: x[0], reverse=True)

    # Save stats
    stats["total_signals"] += len(top_bets) + len(watches)
    stats["total_bets"] += len(top_bets)
    today_key = now.strftime("%Y-%m-%d")
    if today_key not in stats["daily_log"]:
        stats["daily_log"][today_key] = {"bets": []}
    for _, _, s in top_bets:
        stats["daily_log"][today_key]["bets"].append(s)
    save_stats(stats)

    if silent:
        return top_bets, watches

    # Send summary
    lines = [
        "ALIEN PROTOCOL v7",
        today_display,
        f"Win Rate: {win_rate(stats)}% ({stats['wins']}W / {stats['losses']}L)",
        f"Live markets scanned: {len(set(m['city'] for m in live_markets))} cities",
        "─────────────────────",
    ]
    if top_bets:
        lines.append(f"GREEN BETS ({len(top_bets)}):")
        for score, tag, _ in top_bets[:5]:
            lines.append(f"  {tag}")
    if watches:
        lines.append(f"WATCHING ({len(watches)}):")
        for score, tag, _ in watches[:3]:
            lines.append(f"  {tag}")
    if not top_bets and not watches:
        lines.append("No strong signals. Market is well priced today.")
    lines.append("─────────────────────")
    lines.append("Send /bets for full cards with AI verdicts")
    send_telegram("\n".join(lines))

    # Auto send top 3 bet cards
    if top_bets:
        send_telegram("Generating bet cards...")
        for i, (score, tag, s) in enumerate(top_bets[:3], 1):
            verdict = ai_verdict(
                s["city_display"], s["real_temp"], s["market_temp"],
                s["probability"], s["gap"], s["score"],
                s["data_conf"], hour_utc
            )
            card = build_bet_card(s, verdict, i)
            send_telegram(card)
            time.sleep(1)

    print("Scan complete.")
    return top_bets, watches

# ── MORNING BRIEFING ─────────────────────────────────────

def morning_briefing():
    now = datetime.now(timezone.utc)
    stats = load_stats()
    send_telegram(
        f"GOOD MORNING — ALIEN PROTOCOL v7\n"
        f"{now.strftime('%A, %B %d %Y')}\n"
        f"Win Rate: {win_rate(stats)}% ({stats['wins']}W / {stats['losses']}L)\n"
        f"─────────────────────\n"
        f"Scanning today's live Polymarket markets now..."
    )
    run_scan()

# ── EVENING RESULTS ──────────────────────────────────────

def evening_results():
    stats = load_stats()
    today_key = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    today = stats["daily_log"].get(today_key, {"bets": []})
    lines = [
        "EVENING RESULTS — ALIEN PROTOCOL v7",
        today_key,
        "─────────────────────",
        "Check polymarket.com for today's outcomes.",
        "Send /win or /loss for each bet:",
        "─────────────────────",
    ]
    if today["bets"]:
        for i, b in enumerate(today["bets"], 1):
            payout = round(1 / (b["probability"] / 100), 2)
            lines.append(
                f"Bet #{i}: {b['city_display']} {b['market_temp']}C "
                f"@ {b['probability']}% | Payout ${payout}/$1"
            )
    else:
        lines.append("No bets today.")
    lines.append("─────────────────────")
    lines.append(f"Overall: {win_rate(stats)}% ({stats['wins']}W / {stats['losses']}L)")
    send_telegram("\n".join(lines))

# ── COMMAND HANDLER ──────────────────────────────────────

def handle_commands():
    offset = None
    print("Command listener active...")
    while True:
        try:
            updates = get_updates(offset)
            for update in updates:
                offset = update["update_id"] + 1
                msg = update.get("message", {})
                text = msg.get("text", "").strip().lower()
                chat_id = str(msg.get("chat", {}).get("id", ""))
                if chat_id != CHAT_ID:
                    continue

                if text == "/scan":
                    send_telegram("Fetching live Polymarket markets + weather...")
                    run_scan()

                elif text == "/bets":
                    top_bets, _ = run_scan(silent=True)
                    if top_bets:
                        now_hour = datetime.now(timezone.utc).hour
                        send_telegram(f"Top {min(3, len(top_bets))} bet cards:")
                        for i, (score, tag, s) in enumerate(top_bets[:3], 1):
                            verdict = ai_verdict(
                                s["city_display"], s["real_temp"], s["market_temp"],
                                s["probability"], s["gap"], s["score"],
                                s["data_conf"], now_hour
                            )
                            card = build_bet_card(s, verdict, i)
                            send_telegram(card)
                            time.sleep(1)
                    else:
                        send_telegram("No strong signals right now.")

                elif text == "/top":
                    top_bets, _ = run_scan(silent=True)
                    if top_bets:
                        _, _, best = top_bets[0]
                        verdict = ai_verdict(
                            best["city_display"], best["real_temp"], best["market_temp"],
                            best["probability"], best["gap"], best["score"],
                            best["data_conf"], datetime.now(timezone.utc).hour
                        )
                        send_telegram(build_bet_card(best, verdict, 1))
                    else:
                        send_telegram("No strong signals right now.")

                elif text == "/stats":
                    stats = load_stats()
                    send_telegram(
                        f"ALIEN PROTOCOL v7 STATS\n"
                        f"─────────────────────\n"
                        f"Win Rate:      {win_rate(stats)}%\n"
                        f"Wins:          {stats['wins']}\n"
                        f"Losses:        {stats['losses']}\n"
                        f"Total Bets:    {stats['total_bets']}\n"
                        f"Total Signals: {stats['total_signals']}\n"
                        f"─────────────────────\n"
                        f"Stack: Open-Meteo + Tomorrow.io + Groq AI\n"
                        f"Odds: 100% Live from Polymarket"
                    )

                elif text == "/win":
                    stats = load_stats()
                    stats["wins"] += 1
                    save_stats(stats)
                    send_telegram(
                        f"WIN logged.\n"
                        f"Record: {stats['wins']}W / {stats['losses']}L\n"
                        f"Win Rate: {win_rate(stats)}%"
                    )

                elif text == "/loss":
                    stats = load_stats()
                    stats["losses"] += 1
                    save_stats(stats)
                    send_telegram(
                        f"LOSS logged.\n"
                        f"Record: {stats['wins']}W / {stats['losses']}L\n"
                        f"Win Rate: {win_rate(stats)}%"
                    )

                elif text == "/help":
                    send_telegram(
                        "ALIEN PROTOCOL v7 COMMANDS\n"
                        "─────────────────────\n"
                        "/scan  — fetch live markets + scan\n"
                        "/bets  — top 3 bet cards with AI\n"
                        "/top   — single best bet now\n"
                        "/stats — win/loss record\n"
                        "/win   — log a win\n"
                        "/loss  — log a loss\n"
                        "/help  — this menu"
                    )

            time.sleep(2)
        except Exception as e:
            print(f"Command error: {e}")
            time.sleep(5)

# ── SCHEDULER ────────────────────────────────────────────

def scheduler():
    print("Scheduler active...")
    while True:
        now = datetime.now(timezone.utc)
        hour, minute = now.hour, now.minute
        if hour == 6 and minute == 0:
            morning_briefing()
            time.sleep(61)
        elif hour == 22 and minute == 0:
            evening_results()
            time.sleep(61)
        elif minute == 0 and 7 <= hour <= 21:
            run_scan()
            time.sleep(61)
        else:
            time.sleep(30)

# ── MAIN ─────────────────────────────────────────────────

def main():
    send_telegram(
        "ALIEN PROTOCOL v7 ONLINE\n"
        "─────────────────────\n"
        "NEW: Polymarket-first architecture\n"
        "Reads live markets → matches cities → fetches weather\n"
        "No hardcoded cities. No stale odds. 100% dynamic.\n"
        "─────────────────────\n"
        "Commands: /scan /bets /top /stats /win /loss /help\n"
        "Running first scan now..."
    )
    run_scan()
    cmd_thread = threading.Thread(target=handle_commands, daemon=True)
    cmd_thread.start()
    scheduler()

if __name__ == "__main__":
    main()

