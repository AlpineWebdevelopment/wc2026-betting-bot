"""
Telegram bot — sends WC 2026 value bet alerts from Tippmix.
Usage:
  python telegram_bot.py --setup     # find your chat ID
  python telegram_bot.py             # run the bot (checks every N hours)
"""

import sys
import time
import requests
from datetime import datetime

from config import (
    TELEGRAM_TOKEN, TELEGRAM_CHAT_ID,
    TELEGRAM_INTERVAL_HOURS, TELEGRAM_MIN_EDGE, TELEGRAM_BANKROLL,
)

FLASK_URL = "http://localhost:3001"

# ── Country flag emoji lookup (Hungarian team names → flag) ──────────────────
_FLAG: dict[str, str] = {
    # Hosts
    "USA": "🇺🇸", "Egyesült Államok": "🇺🇸",
    "Kanada": "🇨🇦",
    "Mexikó": "🇲🇽",
    # CONMEBOL
    "Argentína": "🇦🇷",
    "Brazília": "🇧🇷",
    "Kolumbia": "🇨🇴",
    "Ecuador": "🇪🇨",
    "Uruguay": "🇺🇾",
    "Venezuela": "🇻🇪",
    "Paraguay": "🇵🇾",
    "Chile": "🇨🇱",
    "Bolívia": "🇧🇴",
    "Peru": "🇵🇪",
    # CONCACAF
    "Panama": "🇵🇦",
    "Costa Rica": "🇨🇷",
    "Honduras": "🇭🇳",
    "Jamaica": "🇯🇲",
    "Guatemala": "🇬🇹",
    "El Salvador": "🇸🇻",
    "Trinidad és Tobago": "🇹🇹",
    # UEFA
    "Franciaország": "🇫🇷",
    "Spanyolország": "🇪🇸",
    "Németország": "🇩🇪",
    "Anglia": "🏴󠁧󠁢󠁥󠁮󠁧󠁿",
    "Portugália": "🇵🇹",
    "Hollandia": "🇳🇱",
    "Belgium": "🇧🇪",
    "Olaszország": "🇮🇹",
    "Svájc": "🇨🇭",
    "Ausztria": "🇦🇹",
    "Horvátország": "🇭🇷",
    "Szerbia": "🇷🇸",
    "Dánia": "🇩🇰",
    "Skócia": "🏴󠁧󠁢󠁳󠁣󠁴󠁿",
    "Magyarország": "🇭🇺",
    "Csehország": "🇨🇿",
    "Szlovákia": "🇸🇰",
    "Lengyelország": "🇵🇱",
    "Románia": "🇷🇴",
    "Törökország": "🇹🇷",
    "Görögország": "🇬🇷",
    "Svédország": "🇸🇪",
    "Norvégia": "🇳🇴",
    "Finnország": "🇫🇮",
    "Ukrajna": "🇺🇦",
    "Albánia": "🇦🇱",
    "Szlovénia": "🇸🇮",
    "Grúzia": "🇬🇪",
    "Wales": "🏴󠁧󠁢󠁷󠁬󠁳󠁿",
    "Izland": "🇮🇸",
    # CAF
    "Marokkó": "🇲🇦",
    "Nigéria": "🇳🇬",
    "Egyiptom": "🇪🇬",
    "Szenegál": "🇸🇳",
    "Ghána": "🇬🇭",
    "Elefántcsontpart": "🇨🇮",
    "Kamerun": "🇨🇲",
    "Dél-Afrika": "🇿🇦",
    "Mali": "🇲🇱",
    "Tunézia": "🇹🇳",
    "Algéria": "🇩🇿",
    "Angola": "🇦🇴",
    "Kongó": "🇨🇬",
    "DR Kongó": "🇨🇩",
    "Mozambik": "🇲🇿",
    "Tanzánia": "🇹🇿",
    "Zambia": "🇿🇲",
    "Etiópia": "🇪🇹",
    # AFC
    "Japán": "🇯🇵",
    "Dél-Korea": "🇰🇷",
    "Ausztrália": "🇦🇺",
    "Irán": "🇮🇷",
    "Szaúd-Arábia": "🇸🇦",
    "Katar": "🇶🇦",
    "Irak": "🇮🇶",
    "Jordánia": "🇯🇴",
    "Üzbegisztán": "🇺🇿",
    "Kína": "🇨🇳",
    "Indonézia": "🇮🇩",
    "Tadzsikisztán": "🇹🇯",
    "Bahrain": "🇧🇭",
    "Kuvait": "🇰🇼",
    "Omán": "🇴🇲",
    # OFC
    "Új-Zéland": "🇳🇿",
}

def _flag(name: str) -> str:
    """Return flag emoji for a team name, or empty string if unknown."""
    return _FLAG.get(name, "")


import os as _os
import atexit

_PID_FILE = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "telegram_bot.pid")

def _write_pid():
    with open(_PID_FILE, "w") as f:
        f.write(str(_os.getpid()))

def _remove_pid():
    try: _os.remove(_PID_FILE)
    except: pass


# ── Telegram helpers ──────────────────────────────────────────────────────────

def _api(method, timeout=15, **kwargs):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/{method}"
    if kwargs:
        r = requests.post(url, json=kwargs, timeout=timeout)
    else:
        r = requests.get(url, timeout=timeout)
    return r.json()


_SILENT = False

def send(text: str, chat_id: str = None):
    _api("sendMessage",
         chat_id=chat_id or TELEGRAM_CHAT_ID,
         text=text,
         parse_mode="HTML",
         disable_notification=_SILENT)


# ── Top-pick logic (mirrors the frontend) ────────────────────────────────────

def _mkt_prio(name: str) -> int:
    if "Döntetlennél" in name:
        return 3
    if "Gólszám" in name:
        return 2
    if name == "1X2":
        return 1
    return 0


def _is_approx(v: dict) -> bool:
    return v.get("market_group") in ("Szögletek", "Statisztika")


def best_picks(vbets: list, min_edge: float) -> tuple:
    """Returns (primary, secondary) mirroring the UI bestPerMatch logic exactly."""
    all_bets = [v for v in vbets if v.get("value")]
    if not all_bets:
        return None, None
    # Trusted: non-approx AND edge >= min_edge, sorted by MKTP desc then edge desc
    trusted = sorted(
        [v for v in all_bets if not _is_approx(v) and v["edge_pct"] >= min_edge],
        key=lambda v: (-_mkt_prio(v["market"]), -v["edge_pct"]),
    )
    # Fallback: best non-approx (if nothing clears min_edge)
    fallback = sorted(
        [v for v in all_bets if not _is_approx(v)],
        key=lambda v: -v["edge_pct"],
    )
    primary = (trusted[0] if trusted else None) or (fallback[0] if fallback else None) or all_bets[0]
    # Secondary = first value bet with different market OR different outcome
    secondary = next(
        (v for v in all_bets
         if v["market"] != primary["market"] or v.get("outcome") != primary.get("outcome")),
        None,
    )
    return primary, secondary


def _stake(v: dict, bankroll: int) -> tuple[int, int]:
    full = max(100, round(bankroll * v["kelly_pct"] / 100 / 100) * 100)
    divisor = 8 if v["market_group"] in ("Szögletek", "Statisztika") else 4
    rec = max(100, round(full / divisor / 100) * 100)
    profit = round(rec * v["best_odds"]) - rec
    return rec, profit


# ── Match formatting ──────────────────────────────────────────────────────────

def format_match(m: dict, pick: dict, rank: int, bankroll: int) -> str:
    rec_stake, rec_profit = _stake(pick, bankroll)
    approx = "~" if pick["market_group"] in ("Szögletek", "Statisztika") else ""
    date_str = m["event_date"][:10] if m.get("event_date") else ""

    return (
        f"{'⭐' if rank == 1 else f'#{rank}'} <b>{m['home_team_hu']} vs {m['away_team_hu']}</b>\n"
        f"📅 {date_str}\n"
        f"\n"
        f"🎯 <b>{pick['market']}</b> — {pick['outcome']}\n"
        f"Odds: <b>{pick['best_odds']}</b>  |  Edge: <b>+{pick['edge_pct']}%</b>{approx}\n"
        f"💰 Javasolt tét: <b>{rec_stake} Ft</b>  →  +{rec_profit} Ft profit\n"
    )


# ── Main check ────────────────────────────────────────────────────────────────

def run_check():
    print(f"[{datetime.now():%H:%M}] Fetching top bets from server...")
    try:
        r = requests.get(f"{FLASK_URL}/top-bets", timeout=60)
        r.raise_for_status()
        top10 = r.json()
    except Exception as e:
        send(f"❌ Szerver hiba: {e}")
        return

    if isinstance(top10, dict) and top10.get("error"):
        send(f"❌ {top10['error']}")
        return

    if not top10:
        print("  No value bets found.")
        send("Nincs value bet jelenleg (min. edge: " + str(TELEGRAM_MIN_EDGE) + "%).")
        return

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    SEP = "—" * 20 + "\n" + "—" * 20

    def block(rank, entry):
        return format_match(entry, entry["bet"], rank, TELEGRAM_BANKROLL)

    # Message 1: header + first 5
    lines1 = [
        SEP,
        f"🌍 <b>VB 2026 Value Betek</b>",
        f"🕐 {now}  |  📊 {len(top10)} bet  |  min. edge {TELEGRAM_MIN_EDGE}%",
        f"💰 Sorrend: Kelly tét szerint (legtöbbet ér először)",
        "",
    ]
    for rank, entry in enumerate(top10[:5], 1):
        lines1.append(block(rank, entry))
    send("\n".join(lines1))

    # Message 2: next 5 (if any) — no separator
    if len(top10) > 5:
        lines2 = ["📋 <b>6–10. helyezett:</b>", ""]
        for rank, entry in enumerate(top10[5:], 6):
            lines2.append(block(rank, entry))
        send("\n".join(lines2))

    print(f"  Sent {len(top10)} bets.")


def run_daily_check():
    """Fetch /bot-daily and send per-match blocks with goal + corner picks."""
    print(f"[{datetime.now():%H:%M}] Fetching daily bets from server...")
    try:
        r = requests.get(f"{FLASK_URL}/bot-daily", timeout=60)
        r.raise_for_status()
        matches = r.json()
    except Exception as e:
        send(f"❌ Szerver hiba: {e}")
        return

    if isinstance(matches, dict) and matches.get("error"):
        send(f"❌ {matches['error']}")
        return

    if not matches:
        send("Nincs value bet ma (min. 10% edge).")
        return

    # Only the next 4 upcoming matches (server already sorts by event_date)
    matches = matches[:4]

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    SEP = "—" * 22

    def _fmt_bet(v, icon, label):
        if not v:
            return ""
        rec, profit = _stake(v, TELEGRAM_BANKROLL)
        return (
            f"{icon} <b>{v['market']}</b> — {v['outcome']}\n"
            f"   odds <b>{v['best_odds']}</b>  |  edge <b>+{v['edge_pct']}%</b>\n"
            f"   💰 <b>{rec:,} Ft</b>  →  +{profit:,} Ft\n"
        )

    header = f"{SEP}\n🌍 <b>VB 2026 — Napi tippek</b>\n🕐 {now}\n{SEP}\n"
    send(header)

    for m in matches:
        dt = ""
        if m.get("event_date"):
            try:
                from datetime import datetime as _dt
                d = _dt.fromisoformat(m["event_date"])
                dt = d.strftime("%m.%d %H:%M")
            except Exception:
                dt = m["event_date"][:16]

        hf = _flag(m["home_team_hu"])
        af = _flag(m["away_team_hu"])
        block = (
            f"🏆 {hf}<b>{m['home_team_hu']}</b> vs {af}<b>{m['away_team_hu']}</b>  📅 {dt}\n\n"
        )
        block += _fmt_bet(m.get("primary_goal"), "⚽", "Match Bot")
        if m.get("secondary_goal"):
            block += _fmt_bet(m["secondary_goal"], "⚽", "Match Bot")
        if m.get("best_corner"):
            block += _fmt_bet(m["best_corner"], "📐", "Corner Bot")

        if block.strip():
            send(block)

    print(f"  Sent {len(matches)} match blocks.")


# ── Setup: find chat ID ───────────────────────────────────────────────────────

def setup():
    if not TELEGRAM_TOKEN:
        print("ERROR: Set TELEGRAM_TOKEN in config.py first.")
        print("  1. Open Telegram, search @BotFather")
        print("  2. Send /newbot, follow the steps")
        print("  3. Copy the token into config.py → TELEGRAM_TOKEN")
        sys.exit(1)

    print("Waiting for a message to your bot...")
    print("  -> Open Telegram and send any message to your bot now.")
    for _ in range(30):
        time.sleep(2)
        data = _api("getUpdates")
        updates = data.get("result", [])
        if updates:
            chat_id = str(updates[-1]["message"]["chat"]["id"])
            print(f"\nYour CHAT_ID is: {chat_id}")
            print(f"   Add this to config.py → TELEGRAM_CHAT_ID = \"{chat_id}\"")
            send("✅ Bot beállítva! Értesítést kapsz, amikor value bet jelenik meg.", chat_id)
            return
    print("No message received. Try again.")


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if "--setup" in sys.argv:
        setup()
        sys.exit(0)

    # Single-instance guard: try to bind a local port — atomic, no race condition
    import socket as _socket
    _lock_sock = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)
    _lock_sock.setsockopt(_socket.SOL_SOCKET, _socket.SO_REUSEADDR, 0)
    try:
        _lock_sock.bind(("127.0.0.1", 47834))
    except OSError:
        print("Bot already running (port 47834 held). Exiting.")
        sys.exit(0)
    _write_pid()
    import atexit
    atexit.register(_remove_pid)
    atexit.register(_lock_sock.close)

    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("ERROR: Set TELEGRAM_TOKEN and TELEGRAM_CHAT_ID in config.py")
        print("  Run: python telegram_bot.py --setup")
        sys.exit(1)

    # Send at fixed times: 11:00, 17:00, 20:00, 23:00
    SEND_HOURS = {11, 18}

    print(f"Bot running — sends at {sorted(SEND_HOURS)} each day (Ctrl+C to stop)\n")

    sent_hours = set()
    while True:
        now_h = datetime.now().hour
        now_min = datetime.now().minute
        if now_h in SEND_HOURS and now_h not in sent_hours:
            run_daily_check()
            sent_hours.add(now_h)
        # Reset at midnight
        if now_h == 0:
            sent_hours.clear()
        time.sleep(60)
