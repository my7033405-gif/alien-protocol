import requests
import csv
import os
import json
import time
import threading
import re
from datetime import datetime, timezone

# ── CONFIG ──────────────────────────────────────────────
TOMORROW_API_KEY = "p2JMu0blVvwGhae9BNTX6A2acUFRoUCi"
OPENWEATHER_KEY  = "2d1986adb664b8bf755e2bb49bb5636d"
GROQ_API_KEY     = "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"
TELEGRAM_TOKEN   = "8232521107:AAEPmqb846XRHt7rZSsXFi-vuPcAcaz8Ogs"
CHAT_ID          = "6637699767"
LOG_FILE         = "signals_v5.csv"
STATS_FILE       = "stats_v5.json"
MIN_SCORE        = 55

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

# ── POLYMARKET AUTO-FETCH ────────────────────────────────

def fetch_polymarket_odds():
    """
    Auto-fetch today's weather temperature odds from Polymarket Gamma API.
    Returns dict: {city_name: {temp_c: probability_%}}
    """
    print("Fetching Polymarket odds...")
    odds = {}
    try:
        url = "https://gamma-api.polymarket.com/markets"
        params = {
            "tag": "temperature",
            "active": "true",
            "closed": "false",
            "limit": 100
        }
        r = requests.get(url, params=params, timeout=30)
        markets = r.json()

        today = datetime.now(timezone.utc).strftime("%B %-d")
        today_alt = datetime.now(timezone.utc).strftime("%b %-d")

        city_names = [c["name"] for c in CITIES]

        for market in markets:
            question = market.get("question", "")
            outcomes = market.get("outcomes", "[]")
            prices = market.get("outcomePrices", "[]")

            # Parse JSON strings if needed
            if isinstance(outcomes, str):
                try:
                    outcomes = json.loads(outcomes)
                except:
                    continue
            if isinstance(prices, str):
                try:
                    prices = json.loads(prices)
                except:
                    continue

            # Match city name in question
            matched_city = None
            for city in city_names:
                if city.lower() in question.lower():
                    matched_city = city
                    break
            if not matched_city:
                continue

            # Only today's markets
            if today.lower() not in question.lower() and today_alt.lower() not in question.lower():
                continue

            # Extract temperature and probability from outcomes
            city_odds = {}
            for i, outcome in enumerate(outcomes):
                if i >= len(prices):
                    break
                try:
                    # Extract temperature number from outcome string
                    temp_match = re.search(r'(-?\d+)', str(outcome))
                    if temp_match:
                        temp = int(temp_match.group(1))
                        prob = round(float(prices[i]) * 100)
                        if 1 <= prob <= 99:
                            city_odds[temp] = prob
                except:
                    continue

            if city_odds:
                if matched_city not in odds:
                    odds[matched_city] = {}
                odds[matched_city].update(city_odds)
                print(f"  Fetched {matched_city}: {city_odds}")

    except Exception as e:
        print(f"Polymarket fetch error: {e}")

    if odds:
        print(f"Auto-fetched odds for {len(odds)} cities.")
    else:
        print("No odds fetched — using fallback odds.")

    return odds

# Fallback odds if API fetch fails
FALLBACK_ODDS = {
    "London":       {19: 31, 18: 27},
    "Tokyo":        {19: 95, 20: 7},
    "Paris":        {23: 37, 22: 24},
    "Toronto":      {2: 42,  1: 37},
    "Sao Paulo":    {29: 45, 28: 35},
    "Seoul":        {12: 37, 13: 24},
    "Shanghai":     {17: 38, 18: 29},
    "Wellington":   {20: 97},
    "Buenos Aires": {18: 90, 19: 6},
    "Hong Kong":    {28: 99, 27: 1},
    "New York":     {10: 50, 11: 30},
    "Berlin":       {16: 44, 15: 30},
    "Madrid":       {22: 88, 23: 15},
    "Sydney":       {24: 35, 25: 20},
    "Singapore":    {33: 50, 34: 30},
}

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
    avg_temp = round(sum(temps) / len(temps), 1)
    sources = "+".join(results.keys())
    if len(temps) == 1:
        confidence = "SINGLE"
    else:
        spread = max(temps) - min(temps)
        if spread <= 1.0:   confidence = "HIGH"
        elif spread <= 2.0: confidence = "MEDIUM"
        else:               confidence = "LOW"
    return avg_temp, sources, confidence

# ── GROQ AI BRAIN ────────────────────────────────────────

def ai_verdict(city, real_temp, market_temp, probability, gap, score, data_conf, hour_utc):
    prompt = f"""You are an expert prediction market trader on Polymarket specializing in weather markets.

Signal to analyze:
- City: {city}
- Real temperature NOW: {real_temp}C
- Market expects: {market_temp}C at {probability}% probability  
- Gap: {gap:+.1f}C (real vs market)
- Confidence score: {score}/100
- Data confidence: {data_conf} (multi-source agreement)
- Time: {hour_utc}:00 UTC

Give me:
1. Should I bet YES on {market_temp}C resolving? 
2. Biggest risk to this trade?
3. Verdict: STRONG BET / BET / PASS / AVOID

Max 3 sentences. Be brutally direct."""

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
        return r.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        return f"AI unavailable: {e}"

# ── STATS ────────────────────────────────────────────────

def load_stats():
    if os.path.exists(STATS_FILE):
        with open(STATS_FILE, "r") as f:
            return json.load(f)
    return {"total_signals": 0, "total_bets": 0, "wins": 0,
            "losses": 0, "daily_log": {}}

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
    if 4 <= hour_utc <= 8:     score += 20
    elif 9 <= hour_utc <= 12:  score += 16
    elif 13 <= hour_utc <= 16: score += 10
    elif 17 <= hour_utc <= 20: score += 5
    else:                      score += 2
    if data_conf == "HIGH":    score += 15
    elif data_conf == "MEDIUM": score += 8
    elif data_conf == "SINGLE": score += 5
    return min(score, 100)

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
            row = {k: v for k, v in s.items() if k in writer.fieldnames}
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
    print(f"\n[{now.strftime('%H:%M UTC')}] ALIEN PROTOCOL v5 scanning...")

    # Auto-fetch Polymarket odds
    live_odds = fetch_polymarket_odds()
    odds_source = "LIVE Polymarket API"
    if not live_odds:
        live_odds = FALLBACK_ODDS
        odds_source = "FALLBACK (manual)"

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
            odds = live_odds.get(city["name"], {})
            if not odds:
                continue
            for market_temp, probability in odds.items():
                gap = round(temp - market_temp, 1)
                score = confidence_score(gap, probability, hour_utc, data_conf)
                if gap >= 2 and probability < 40:
                    rating = "BET"
                elif gap >= 1 and probability < 50:
                    rating = "WATCH"
                else:
                    rating = "SKIP"
                s = {
                    "city": city["name"],
                    "real_temp": temp,
                    "market_temp": market_temp,
                    "market_prob": probability,
                    "gap": gap,
                    "score": score,
                    "rating": rating,
                    "sources": sources,
                    "data_conf": data_conf,
                }
                all_signals.append(s)
                tag = (f"[{score}] {city['name']}: "
                       f"Real {temp}C vs {market_temp}C "
                       f"@ {probability}% | Gap {gap:+.1f} [{data_conf}]")
                if rating == "BET" and score >= MIN_SCORE:
                    top_bets.append((score, tag, s))
                    print(f"  GREEN  {tag}")
                elif rating == "WATCH" and score >= MIN_SCORE - 10:
                    watches.append((score, tag, s))
                    print(f"  YELLOW {tag}")
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

    lines = [
        "ALIEN PROTOCOL v5",
        f"{now.strftime('%Y-%m-%d %H:%M UTC')}",
        f"Odds: {odds_source}",
        f"Win Rate: {win_rate(stats)}% ({stats['wins']}W/{stats['losses']}L)",
        "─────────────────────",
    ]
    if top_bets:
        lines.append(f"GREEN BETS ({len(top_bets)}):")
        for score, tag, _ in top_bets[:5]:
            lines.append(f"  {tag}")
    if watches:
        lines.append(f"YELLOW WATCHES ({len(watches)}):")
        for score, tag, _ in watches[:3]:
            lines.append(f"  {tag}")
    if not top_bets and not watches:
        lines.append("No strong signals. Market well-priced today.")
    lines.append("─────────────────────")
    lines.append(f"Cities: {len(CITIES)} | Signals: {len(all_signals)}")
    send_telegram("\n".join(lines))

    # AI verdict on top signal
    if top_bets:
        _, _, best = top_bets[0]
        verdict = ai_verdict(
            best["city"], best["real_temp"], best["market_temp"],
            best["market_prob"], best["gap"], best["score"],
            best["data_conf"], hour_utc
        )
        send_telegram(
            f"AI VERDICT — TOP SIGNAL\n"
            f"─────────────────────\n"
            f"{best['city']} YES {best['market_temp']}C @ {best['market_prob']}%\n"
            f"Score: {best['score']}/100 | {best['data_conf']}\n"
            f"Gap: {best['gap']:+.1f}C\n"
            f"─────────────────────\n"
            f"{verdict}\n"
            f"─────────────────────\n"
            f"Go to polymarket.com → Weather → {best['city']}"
        )

    print("Scan complete.")
    return top_bets, watches

# ── MORNING BRIEFING ─────────────────────────────────────

def morning_briefing():
    now = datetime.now(timezone.utc)
    top_bets, _ = run_scan(silent=True)
    stats = load_stats()
    lines = [
        "GOOD MORNING — ALIEN PROTOCOL v5",
        now.strftime("%A, %B %d"),
        f"Win Rate: {win_rate(stats)}% ({stats['wins']}W/{stats['losses']}L)",
        "─────────────────────",
    ]
    if top_bets:
        lines.append(f"TOP {min(3, len(top_bets))} SIGNALS:")
        for score, tag, _ in top_bets[:3]:
            lines.append(f"  {tag}")
        _, _, best = top_bets[0]
        verdict = ai_verdict(
            best["city"], best["real_temp"], best["market_temp"],
            best["market_prob"], best["gap"], best["score"],
            best["data_conf"], now.hour
        )
        lines.append("─────────────────────")
        lines.append("AI on best signal:")
        lines.append(verdict)
        lines.append("─────────────────────")
        lines.append(f"Bet link: polymarket.com → Weather → {best['city']}")
    else:
        lines.append("No strong signals today. Skip — protect the bankroll.")
    send_telegram("\n".join(lines))
    print("Morning briefing sent.")

# ── EVENING RESULTS ──────────────────────────────────────

def evening_results():
    stats = load_stats()
    today_key = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    today = stats["daily_log"].get(today_key, {"bets": []})
    lines = [
        "EVENING RESULTS — ALIEN PROTOCOL v5",
        today_key,
        "─────────────────────",
        "Check polymarket.com for today's outcomes.",
        "Send /win or /loss for each:",
        "─────────────────────",
    ]
    if today["bets"]:
        for b in today["bets"]:
            lines.append(
                f"  {b['city']} {b['market_temp']}C "
                f"@ {b['market_prob']}% | Score {b['score']}"
            )
    else:
        lines.append("No bets today.")
    lines.append("─────────────────────")
    lines.append(f"Record: {win_rate(stats)}% ({stats['wins']}W/{stats['losses']}L)")
    send_telegram("\n".join(lines))

# ── COMMAND HANDLER ──────────────────────────────────────

def handle_commands():
    offset = None
    print("Commands active: /scan /stats /top /win /loss /help")
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
                    send_telegram("Scanning + fetching live Polymarket odds...")
                    run_scan()
                elif text == "/stats":
                    stats = load_stats()
                    send_telegram(
                        f"ALIEN PROTOCOL v5 STATS\n"
                        f"─────────────────────\n"
                        f"Win Rate:      {win_rate(stats)}%\n"
                        f"Wins:          {stats['wins']}\n"
                        f"Losses:        {stats['losses']}\n"
                        f"Total Bets:    {stats['total_bets']}\n"
                        f"Total Signals: {stats['total_signals']}\n"
                        f"Stack: Open-Meteo+Tomorrow.io+Groq AI\n"
                        f"Odds: Live Polymarket API"
                    )
                elif text == "/top":
                    send_telegram("Finding top signal...")
                    top_bets, _ = run_scan(silent=True)
                    if top_bets:
                        _, _, best = top_bets[0]
                        verdict = ai_verdict(
                            best["city"], best["real_temp"], best["market_temp"],
                            best["market_prob"], best["gap"], best["score"],
                            best["data_conf"], datetime.now(timezone.utc).hour
                        )
                        send_telegram(
                            f"TOP SIGNAL + AI VERDICT\n"
                            f"─────────────────────\n"
                            f"{best['city']} YES {best['market_temp']}C "
                            f"@ {best['market_prob']}%\n"
                            f"Score: {best['score']}/100 | Gap: {best['gap']:+.1f}C\n"
                            f"─────────────────────\n"
                            f"{verdict}\n"
                            f"─────────────────────\n"
                            f"polymarket.com → Weather → {best['city']}"
                        )
                    else:
                        send_telegram("No strong signals right now. Wait.")
                elif text == "/win":
                    stats = load_stats()
                    stats["wins"] += 1
                    save_stats(stats)
                    send_telegram(
                        f"WIN logged.\n"
                        f"Record: {stats['wins']}W/{stats['losses']}L\n"
                        f"Win Rate: {win_rate(stats)}%"
                    )
                elif text == "/loss":
                    stats = load_stats()
                    stats["losses"] += 1
                    save_stats(stats)
                    send_telegram(
                        f"LOSS logged.\n"
                        f"Record: {stats['wins']}W/{stats['losses']}L\n"
                        f"Win Rate: {win_rate(stats)}%"
                    )
                elif text == "/help":
                    send_telegram(
                        "ALIEN PROTOCOL v5 COMMANDS\n"
                        "─────────────────────\n"
                        "/scan  — live scan + AI verdict\n"
                        "/stats — win/loss record\n"
                        "/top   — best signal + AI now\n"
                        "/win   — log a win\n"
                        "/loss  — log a loss\n"
                        "/help  — this menu\n"
                        "─────────────────────\n"
                        "Auto: 6am briefing, hourly scans, 10pm results"
                    )
            time.sleep(2)
        except Exception as e:
            print(f"Command error: {e}")
            time.sleep(5)

# ── SCHEDULER ────────────────────────────────────────────

def scheduler():
    print("Scheduler active — auto-scan every hour 7am-10pm UTC")
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
        "ALIEN PROTOCOL v5 ONLINE\n"
        "─────────────────────\n"
        "Weather: Open-Meteo + Tomorrow.io + OpenWeatherMap\n"
        "Odds: Live Polymarket API (auto-fetch)\n"
        "Brain: Groq AI Llama 3 70B\n"
        "Cities: 15 global markets\n"
        "Schedule: 6am briefing, hourly scans, 10pm results\n"
        "─────────────────────\n"
        "FULLY AUTONOMOUS. No manual updates needed.\n"
        "Commands: /scan /stats /top /win /loss /help\n"
        "─────────────────────\n"
        "Running first scan now..."
    )
    run_scan()
    cmd_thread = threading.Thread(target=handle_commands, daemon=True)
    cmd_thread.start()
    scheduler()

if __name__ == "__main__":
    main()
