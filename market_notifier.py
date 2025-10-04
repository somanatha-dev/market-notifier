#!/usr/bin/env python3
"""
market_notifier.py
GitHub Actions scheduled runner that:
- Checks Nifty intraday using yfinance (POC)
- Sends Telegram notifications for:
    * Crash triggers (Nifty <= -3% in that run)
    * EOD summary (run at 18:30 IST cron)
- Persists crash deployment state to crash_state.json (committed back by the workflow)

Notes:
- Replace fetch_market_data() with a stronger data provider if you need more accuracy.
- Environment variables expected (set as repo secrets):
    TELEGRAM_BOT_TOKEN
    TELEGRAM_CHAT_ID
"""
import os
import json
import math
import datetime
import pytz
import requests
import yfinance as yf

# ---------- CONFIG ----------
CRASH_SEQUENCE = [20000, 20000, 10000, 20000, 20000, 10000]
FUNDS = [
    "Navi Nifty India Manufacturing Index Fund",
    "Navi Flexi Cap Fund",
    "Navi Nifty Midcap 150 Index Fund",
    "Navi Nifty 50 Index Fund",
]
VIX_THRESHOLD = 20.0
STATE_FILE = "crash_state.json"
IST = pytz.timezone("Asia/Kolkata")
# threshold for crash trigger (percentage)
CRASH_TRIGGER_PCT = -3.0
# ----------------------------

# Secrets / env
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID") or os.getenv("CHAT_ID")

def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                return json.load(f)
        except Exception:
            return {"deployed": [False] * len(CRASH_SEQUENCE)}
    return {"deployed": [False] * len(CRASH_SEQUENCE)}

def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)

def now_ist():
    return datetime.datetime.now(pytz.utc).astimezone(IST)

def fetch_market_data():
    """
    POC: Uses yfinance to fetch intraday Nifty close vs open for the day.
    Replace this implementation with a better provider for production use:
    - Sensex, Nifty, India VIX, FII/DII flows, top movers, news snippets.
    """
    try:
        ticker = yf.Ticker("^NSEI")  # common shorthand for NIFTY (may vary)
        hist = ticker.history(period="1d", interval="5m")
        if hist.empty:
            return {"error": "no data from yfinance"}
        open_price = float(hist['Close'].iloc[0])
        last = float(hist['Close'].iloc[-1])
        pct = round((last - open_price) / open_price * 100, 2)
        return {
            "nifty_pct": pct,
            "nifty_price": last,
            "time": now_ist().strftime("%Y-%m-%d %H:%M IST"),
            "vix": None,
            "fii": None,
            "dii": None,
            "top_movers": []
        }
    except Exception as e:
        return {"error": f"fetch error: {e}"}

def compute_allocation(amount, vix):
    """
    Given total amount and current VIX (or None), returns a dict fund->amount (rupees).
    Uses your rules: normally 25% each. If vix>VIX_THRESHOLD, reduce midcap to 10% and reallocate.
    Rounding uses floor + put remainder in first fund to ensure sum == amount.
    """
    if vix is not None and vix > VIX_THRESHOLD:
        weights = [0.25, 0.325, 0.10, 0.325]
    else:
        weights = [0.25, 0.25, 0.25, 0.25]
    per = [math.floor(amount * w) for w in weights]
    diff = amount - sum(per)
    per[0] += diff
    return dict(zip(FUNDS, per))

def send_telegram(text):
    if not BOT_TOKEN or not CHAT_ID:
        print("Missing TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID. Skipping Telegram send.")
        return False
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": text}
    try:
        r = requests.post(url, data=payload, timeout=15)
        if r.status_code == 200:
            print("Telegram sent")
            return True
        else:
            print("Telegram send failed", r.status_code, r.text)
            return False
    except Exception as e:
        print("Telegram send exception:", e)
        return False

def format_eod(payload, state):
    # Minimal EOD template you approved
    return (
        f"EOD Market Summary — {now_ist().strftime('%Y-%m-%d %H:%M IST')}\n"
        f"1) Market headline: Nifty {payload.get('nifty_pct')}% ({payload.get('nifty_price')})\n"
        f"2) Top sectors ↑: (fetch externally) ; Top sectors ↓: (fetch externally)\n"
        f"3) Notable movers: {', '.join(payload.get('top_movers', [])[:3]) or 'N/A'}\n"
        f"4) Catalysts: (summarize Reuters / ET / Mint / Bloomberg externally)\n"
        f"5) Macro / flows: FII {payload.get('fii')} | DII {payload.get('dii')} | VIX {payload.get('vix')}\n"
        f"6) Events ahead: (RBI / US jobs / results - fill externally)\n"
        f"7) Personal plan status: SIP ₹500 ×4 = ₹2000 | Crashes used: {sum(state['deployed'])}/{len(state['deployed'])}\n"
        f"8) Suggested next step: No action unless specified.\n"
    )

def is_eod_run():
    """
    The workflow runs at 18:30 IST via cron. We also check the local IST time to be safe.
    Return True if current IST time matches 18:30 (±1 minute tolerance).
    """
    now = now_ist()
    return now.hour == 18 and now.minute in (30, 31)

def run_check():
    state = load_state()
    data = fetch_market_data()
    if 'error' in data:
        send_telegram(f"Market fetch error: {data.get('error')}")
        return state

    # EOD: the workflow runs an EOD cron; this double-check ensures proper message too.
    if is_eod_run():
        send_telegram(format_eod(data, state))
        return state

    nifty_pct = data.get('nifty_pct')
    if nifty_pct is None:
        print("No nifty_pct available; skipping")
        return state

    # Crash trigger
    if nifty_pct <= CRASH_TRIGGER_PCT:
        try:
            idx = state['deployed'].index(False)
        except ValueError:
            idx = None
        if idx is not None:
            amount = CRASH_SEQUENCE[idx]
            alloc = compute_allocation(amount, data.get("vix"))
            state['deployed'][idx] = True
            text = f"MARKET DROP ≥3% — {data.get('time')}\n"
            text += f"Nifty {nifty_pct}%\n"
            text += f"Action: Crash #{idx+1} → Deploy ₹{amount}\n"
            text += "Allocations (normal or VIX-adjusted):\n"
            for f, a in alloc.items():
                text += f"• {f}: ₹{a}\n"
            text += "Tranches (3) — split roughly equally at 10:15 / 12:30 / 14:50 (adjust if close).\n"
            text += f"Crashes used: {sum(state['deployed'])}/{len(state['deployed'])}\n"
            send_telegram(text)
        else:
            print("Crash detected but all crash tranches already deployed.")
    else:
        print(f"No crash. Nifty pct {nifty_pct}%")

    return state

if __name__ == "__main__":
    new_state = run_check()
    save_state(new_state)
    print("Run completed at", now_ist().strftime("%Y-%m-%d %H:%M IST"))
