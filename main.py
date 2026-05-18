import requests
import csv
import os
import json
import time
import threading
from datetime import datetime, timezone

# ── CONFIG ──────────────────────────────────────────────
TOMORROW_API_KEY = "p2JMu0blVvwGhae9BNTX6A2acUFRoUCi"
OPENWEATHER_KEY  = "2d1986adb664b8bf755e2bb49bb5636d"
GROQ_API_KEY     = "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"
TELEGRAM_TOKEN   = "8232521107:AAEPmqb846XRHt7rZSsXFi-vuPcAcaz8Ogs"
CHAT_ID          = "6637699767"
LOG_FILE         = "signals_v6.csv"
STATS_FILE       = "stats_v6.json"
MIN_SCORE        = 60

CITIES = [
    {"name": "London",       "lat": 51.5074,  "lon": -0.1278},
    {"name": "Tokyo",        "lat": 35.6762,  "lon": 139.6503},
    {"name": "Paris",        "lat": 48.8566,  "lon":  2.3522},
    {"name": "Toronto",      "lat": 43.6510,  "lon": -79.3470},
    {"name": "Sao Paulo",    "lat": -23.5505, "lon": -46.6333},
    {"name": "Seoul",        "lat": 37.5665,  "lon": 126.9780},
    {"name": "Shanghai",     "lat": 31.2304,  "lon": 121.4737},
    {"name": "Wellington",   "lat": -41.2866, "lon": 174.7756},
    {"name": "Buenos Aires", "lat": -34.6037, "lon": -58.3816},
    {"name": "Hong Kong",    "lat": 22.3193,  "lon": 114.1694},
    {"name": "New York",     "lat": 40.7128,  "lon": -74.0060},
    {"name": "Berlin",       "lat": 52.5200,  "lon":  13.4050},
    {"name": "Madrid",       "lat": 40.4168,  "lon": -3.7038},
    {"name": "Sydney",       "lat": -33.8688, "lon": 151.2093},
    {"name": "Singapore",    "lat":  1.3521,  "lon": 103.8198},
]

# ── POLYMARKET LIVE ODDS ─────────────────────────────────
# Market type is HIGHEST temperature — always verify on site

def fetch_polymarket_odds():
    print("  Fetching live Polymarket odds...")
    try:
        today = datetime.now(timezone.utc)
        date_str = today.strftime("%B %-d")  # e.g. "May 18"
        url = "https://gamma-api.polymarket.com/markets?active=true&closed=false&limit=200"
        r = requests.get(url, timeout=30)
        markets = r.json()

        odds = {}
        city_keywords = {
            "London": "london", "Tokyo": "tokyo", "Paris": "paris",
            "Toronto": "toronto", "Sao Paulo": "paulo", "Seoul": "seoul",
            "Shanghai": "shanghai", "Wellington": "wellington",
            "Buenos Aires": "buenos", "Hong Kong": "hong kong",
            "New York": "new york", "Berlin": "berlin",
            "Madrid": "madrid", "Sydney": "sydney", "Singapore": "singapore",
        }

        for market in markets:
            title = market.get("question", "").lower()
            # Only target HIGHEST temperature markets
            if "highest" not in title:
                continue

            for city, keyword in city_keywords.items():
                if keyword not in title:
                    continue
                try:
                    import re
                    outcomes = market.get("outcomes", "[]")
                    prices = market.get("outcomePrices", "[]")
                    if isinstance(outcomes, str):
                        outcomes = json.loads(outcomes)
                    if isinstance(prices, str):
                        prices = json.loads(prices)

                    if city not in odds:
                        odds[city] = {}

                    for i, outcome in enumerate(outcomes):
                        temp_match = re.search(r'(-?\d+)', str(outcome))
                        if temp_match and i < len(prices):
                            temp = int(temp_match.group(1))
                            prob = round(float(prices[i]) * 100, 1)
                            if prob > 1:  # ignore dust markets
                                odds[city][temp] = prob
                except Exception as e:
                    print(f"    Parse error {city}: {e}")
                break

        if odds:
            print(f"  Got live odds for {len(odds)} cities")
            return odds
        else:
            print("  No live odds found — using fallback")
            return None

    except Exception as e:
        print(f"  Polymarket error: {e}")
        return None

FALLBACK_ODDS = {
    "London":       {19: 31, 18: 27},
    "Tokyo":        {21: 45, 22: 30},
    "Paris":        {23: 37, 22: 24},
    "Toronto":      {18: 40, 19: 25},
    "Sao Paulo":    {29: 45, 28: 35},
    "Seoul":        {24: 37, 25: 24},
    "Shanghai":     {28: 38, 29: 29},
    "Wellington":   {14: 60, 15: 25},
    "Buenos Aires": {18: 50, 19: 30},
    "Hong Kong":    {30: 45, 31: 30},
    "New York":     {28: 40, 29: 30},
    "Berlin":       {20: 44, 21: 30},
    "Madrid":       {26: 45, 27: 30},
    "Sydney":       {20: 45, 21: 30},
    "Singapore":    {33: 50, 34: 30},
}

# ── POLYMARKET SEARCH LINK ───────────────────────────────

def polymarket_link(city):
    today = datetime.now(timezone.utc)
    month = today.strftime("%B").lower()
    day = today.day
    city_slug = city.lower().replace(" ", "-")
    return f"https://polymarket.com/event/highest-temperature-in-{city_slug}-on-{month}-{day}"

# ── WEATHER APIS ─────────────────────────────────────────

def get_openmeteo(city):
    url = (
        f"https://api.open-meteo.com/v1/forecast"
        f"?latitude={city['lat']}&longitude={city['lon']}"
        f"&daily=temperature_2m_max&timezone=UTC&forecast_days=1"
    )
    r = requests.get(url, timeout=30)
    data = r.json()
    temps = data.get("daily", {}).get("temperature_2m_max", [])
    return round(float(temps[0]), 1) if temps else None

def get_tomorrow(city):
    url = (
        f"https://api.tomorrow.io/v4/weather/forecast"
        f"?location={city['lat']},{city['lon']}"
        f"&timesteps=1d&units=metric&apikey={TOMORROW_API_KEY}"
    )
    r = requests.get(url, timeout=30)
    data = r.json()
    try:
        today = data["timelines"]["daily"][0]["values"]
        return round(float(today["temperatureMax"]), 1)
    except:
        return None

def get_openweather(city):
    url = (
        f"https://api.openweathermap.org/data/2.5/forecast"
        f"?lat={city['lat']}&lon={city['lon']}"
        f"&appid={OPENWEATHER_KEY}&units=metric"
    )
    r = requests.get(url, timeout=30)
    data = r.json()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    temps = [
        item["main"]["temp_max"]
        for item in data.get("list", [])
        if item["dt_txt"].startswith(today)
    ]
    return round(max(temps), 1) if temps else None

def get_best_temp(city):
    results = {}
    try:
        t = get_openmeteo(city)
        if t: results["Open-Meteo"] = t
    except: pass
    try:
        t = get_tomorrow(city)
        if t: results["Tomorrow.io"] = t
    except: pass
    if not results:
        try:
            t = get_openweather(city)
            if t: results["OpenWeatherMap"] = t
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

# ── GROQ AI ──────────────────────────────────────────────

def ai_verdict(city, real_temp, market_temp, probability, gap, score, data_conf, hour_utc):
    prompt = (
        f"You are a Polymarket weather trading expert.\n\n"
        f"Signal:\n"
        f"- City: {city}\n"
        f"- Real max temp today: {real_temp}C\n"
        f"- Market: Highest temp = {market_temp}C at {probability}% probability\n"
        f"- Gap: {gap:+.1f}C above market expectation\n"
        f"- Score: {score}/100\n"
        f"- Data confidence: {data_conf}\n"
        f"- UTC hour: {hour_utc}:00\n\n"
        f"Answer in exactly 3 lines:\n"
        f"1. Should I bet YES on {market_temp}C resolving? Why?\n"
        f"2. Biggest risk?\n"
        f"3. Final verdict: STRONG BET / BET / PASS / AVOID"
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
                "max_tokens": 150,
                "temperature": 0.2
            },
            timeout=30
        )
        data = r.json()
        return data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        return f"AI error: {e}"

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

# ── CONFIDENCE SCORER ────────────────────────────────────

def confidence_score(gap, probability, hour_utc, data_conf):
    score = 0
    if gap >= 6:   score += 35
    elif gap >= 4: score += 28
    elif gap >= 3: score += 21
    elif gap >= 2: score += 14
    elif gap >= 1: score += 7
    if probability <= 15:   score += 30
    elif probability <= 25: score += 24
    elif probability <= 35: score += 18
    elif probability <= 45: score += 12
    elif probability <= 55: score += 6
    if 4 <= hour_utc <= 8:      score += 20
    elif 9 <= hour_utc <= 12:   score += 16
    elif 13 <= hour_utc <= 16:  score += 10
    elif 17 <= hour_utc <= 20:  score += 5
    else:                       score += 2
    if data_conf == "HIGH":     score += 15
    elif data_conf == "MEDIUM": score += 8
    elif data_conf == "SINGLE": score += 5
    return min(score, 100)

# ── SIGNAL BUILDER ───────────────────────────────────────

def build_signals(city_name, real_temp, odds, hour_utc, sources, data_conf):
    signals = []
    for market_temp, probability in odds.items():
        gap = real_temp - market_temp
        score = confidence_score(gap, probability, hour_utc, data_conf)
        if gap >= 2 and probability < 40:
            rating = "BET"
        elif gap >= 1 and probability < 50:
            rating = "WATCH"
        else:
            rating = "SKIP"
        signals.append({
            "city": city_name,
            "real_temp": real_temp,
            "market_temp": market_temp,
            "market_prob": probability,
            "gap": gap,
            "score": score,
            "rating": rating,
            "sources": sources,
            "data_conf": data_conf,
        })
    return signals

# ── BET CARD ─────────────────────────────────────────────

def build_bet_card(s, verdict, rank):
    payout = round(1 / (s["market_prob"] / 100), 2)
    return (
        f"BET #{rank} — {s['city'].upper()}\n"
        f"─────────────────────\n"
        f"Market: Highest temp = {s['market_temp']}C\n"
        f"Market says: {s['market_prob']}% chance\n"
        f"Real temp now: {s['real_temp']}C\n"
        f"Gap: {s['gap']:+.1f}C above expectation\n"
        f"Score: {s['score']}/100\n"
        f"Data: {s['sources']}\n"
        f"Confidence: {s['data_conf']}\n"
        f"Payout if win: ${payout} per $1 bet\n"
        f"─────────────────────\n"
        f"AI VERDICT:\n{verdict}\n"
        f"─────────────────────\n"
        f"WHERE TO BET:\n"
        f"polymarket.com → Weather → Temperature\n"
        f"Search: 'Highest temperature {s['city']}'\n"
        f"Click YES on {s['market_temp']}C"
    )

# ── CSV LOGGER ───────────────────────────────────────────

def log_to_csv(signals):
    file_exists = os.path.exists(LOG_FILE)
    with open(LOG_FILE, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "timestamp", "city", "real_temp", "market_temp",
            "market_prob", "gap", "score", "rating", "sources", "data_conf"
        ])
        if not file_exists:
            writer.writeheader()
        for s in signals:
            row = dict(s)
            row["timestamp"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
            writer.writerow(row)

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

# ── SCAN ENGINE ──────────────────────────────────────────

def run_scan(silent=False):
    now = datetime.now(timezone.utc)
    hour_utc = now.hour
    print(f"\n[{now.strftime('%H:%M UTC')}] Scanning {len(CITIES)} cities...")

    live_odds = fetch_polymarket_odds()
    polymarket_odds = live_odds if live_odds else FALLBACK_ODDS
    odds_source = "LIVE Polymarket" if live_odds else "FALLBACK"

    all_signals = []
    top_bets = []
    watches = []
    stats = load_stats()

    for city in CITIES:
        try:
            temp, sources, data_conf = get_best_temp(city)
            if temp is None:
                print(f"  NO DATA   {city['name']}")
                continue
            odds = polymarket_odds.get(city["name"], {})
            if not odds:
                continue
            signals = build_signals(city["name"], temp, odds, hour_utc, sources, data_conf)
            all_signals.extend(signals)
            for s in signals:
                tag = (f"[{s['score']}] {city['name']}: "
                       f"Real {temp}C vs {s['market_temp']}C "
                       f"@ {s['market_prob']}% | Gap {s['gap']:+.1f} [{data_conf}]")
                if s["rating"] == "BET" and s["score"] >= MIN_SCORE:
                    top_bets.append((s["score"], tag, s))
                    print(f"  GREEN  {tag}")
                elif s["rating"] == "WATCH" and s["score"] >= MIN_SCORE - 10:
                    watches.append((s["score"], tag, s))
                    print(f"  WATCH  {tag}")
                else:
                    print(f"  SKIP   {tag}")
        except Exception as e:
            print(f"  ERROR {city['name']}: {e}")

    top_bets.sort(key=lambda x: x[0], reverse=True)
    watches.sort(key=lambda x: x[0], reverse=True)

    if all_signals:
        log_to_csv(all_signals)
        stats["total_signals"] += len(all_signals)
        stats["total_bets"] += len(top_bets)
        today_key = now.strftime("%Y-%m-%d")
        if today_key not in stats["daily_log"]:
            stats["daily_log"][today_key] = {"bets": [], "results": []}
        for _, _, s in top_bets:
            stats["daily_log"][today_key]["bets"].append(s)
        save_stats(stats)

    if silent:
        return top_bets, watches

    # Summary report
    lines = [
        "ALIEN PROTOCOL v6",
        f"{now.strftime('%Y-%m-%d %H:%M UTC')}",
        f"Odds source: {odds_source}",
        f"Win Rate: {win_rate(stats)}% ({stats['wins']}W / {stats['losses']}L)",
        "─────────────────────",
    ]
    if top_bets:
        lines.append(f"TOP BETS TODAY ({len(top_bets)}):")
        for score, tag, _ in top_bets[:5]:
            lines.append(f"  {tag}")
    if watches:
        lines.append(f"WATCHING ({len(watches)}):")
        for score, tag, _ in watches[:3]:
            lines.append(f"  {tag}")
    if not top_bets and not watches:
        lines.append("No strong signals. Market well-priced today.")
    lines.append("─────────────────────")
    lines.append(f"Cities: {len(CITIES)} | Total signals: {len(all_signals)}")
    lines.append("Send /bets for full bet cards with AI verdicts")
    send_telegram("\n".join(lines))

    # Auto send top 3 bet cards
    if top_bets:
        send_telegram("Generating bet cards...")
        for i, (score, tag, s) in enumerate(top_bets[:3], 1):
            verdict = ai_verdict(
                s["city"], s["real_temp"], s["market_temp"],
                s["market_prob"], s["gap"], s["score"],
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
    top_bets, _ = run_scan(silent=True)
    stats = load_stats()
    lines = [
        "GOOD MORNING — ALIEN PROTOCOL v6",
        now.strftime("%A, %B %d"),
        f"Win Rate: {win_rate(stats)}% ({stats['wins']}W / {stats['losses']}L)",
        "─────────────────────",
    ]
    if top_bets:
        lines.append(f"TOP SIGNALS TODAY ({len(top_bets)}):")
        for score, tag, _ in top_bets[:5]:
            lines.append(f"  {tag}")
        lines.append("─────────────────────")
        lines.append("Send /bets for full details + AI verdicts on each.")
        lines.append("Bet $1 each on scores 70+. Max 3 bets.")
    else:
        lines.append("No strong signals today. Sit on your hands.")
    send_telegram("\n".join(lines))

# ── EVENING RESULTS ──────────────────────────────────────

def evening_results():
    stats = load_stats()
    today_key = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    today = stats["daily_log"].get(today_key, {"bets": []})
    lines = [
        "EVENING RESULTS — ALIEN PROTOCOL v6",
        today_key,
        "─────────────────────",
        "Check polymarket.com for today's outcomes.",
        "Send /win or /loss for each:",
        "─────────────────────",
    ]
    if today["bets"]:
        for i, b in enumerate(today["bets"], 1):
            payout = round(1 / (b["market_prob"] / 100), 2)
            lines.append(
                f"Bet #{i}: {b['city']} {b['market_temp']}C "
                f"@ {b['market_prob']}% | "
                f"Payout: ${payout}/$1"
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
                    send_telegram("Scanning 15 cities + fetching live odds...")
                    run_scan()

                elif text == "/bets":
                    top_bets, _ = run_scan(silent=True)
                    if top_bets:
                        now_hour = datetime.now(timezone.utc).hour
                        send_telegram(f"Generating {min(3, len(top_bets))} bet cards...")
                        for i, (score, tag, s) in enumerate(top_bets[:3], 1):
                            verdict = ai_verdict(
                                s["city"], s["real_temp"], s["market_temp"],
                                s["market_prob"], s["gap"], s["score"],
                                s["data_conf"], now_hour
                            )
                            card = build_bet_card(s, verdict, i)
                            send_telegram(card)
                            time.sleep(1)
                    else:
                        send_telegram("No strong signals right now. Check back later.")

                elif text == "/stats":
                    stats = load_stats()
                    send_telegram(
                        f"ALIEN PROTOCOL v6 STATS\n"
                        f"─────────────────────\n"
                        f"Win Rate:      {win_rate(stats)}%\n"
                        f"Wins:          {stats['wins']}\n"
                        f"Losses:        {stats['losses']}\n"
                        f"Total Bets:    {stats['total_bets']}\n"
                        f"Total Signals: {stats['total_signals']}\n"
                        f"─────────────────────\n"
                        f"Weather: Open-Meteo + Tomorrow.io\n"
                        f"Brain: Groq Llama 3 70B\n"
                        f"Odds: Live Polymarket API"
                    )

                elif text == "/top":
                    top_bets, _ = run_scan(silent=True)
                    if top_bets:
                        _, _, best = top_bets[0]
                        verdict = ai_verdict(
                            best["city"], best["real_temp"], best["market_temp"],
                            best["market_prob"], best["gap"], best["score"],
                            best["data_conf"], datetime.now(timezone.utc).hour
                        )
                        send_telegram(build_bet_card(best, verdict, 1))
                    else:
                        send_telegram("No strong signals right now.")

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
                        "ALIEN PROTOCOL v6 COMMANDS\n"
                        "─────────────────────\n"
                        "/scan  — full scan + live odds\n"
                        "/bets  — top 3 bet cards with AI\n"
                        "/top   — single best bet card\n"
                        "/stats — win/loss record\n"
                        "/win   — log a win\n"
                        "/loss  — log a loss\n"
                        "/help  — this menu\n"
                        "─────────────────────\n"
                        "All markets are HIGHEST temperature.\n"
                        "Never bet LOWEST temperature markets."
                    )

            time.sleep(2)
        except Exception as e:
            print(f"Command error: {e}")
            time.sleep(5)

# ── SCHEDULER ────────────────────────────────────────────

def scheduler():
    print("Scheduler active — hourly 7am-10pm UTC")
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
        "ALIEN PROTOCOL v6 ONLINE\n"
        "─────────────────────\n"
        "Weather: Open-Meteo + Tomorrow.io + OpenWeatherMap\n"
        "Odds: Live Polymarket API (HIGHEST temp markets only)\n"
        "Brain: Groq AI Llama 3 70B\n"
        "Cities: 15 global markets\n"
        "─────────────────────\n"
        "Commands: /scan /bets /top /stats /win /loss /help\n"
        "─────────────────────\n"
        "Running first scan now..."
    )
    run_scan()
    cmd_thread = threading.Thread(target=handle_commands, daemon=True)
    cmd_thread.start()
    scheduler()

if __name__ == "__main__":
    main()

