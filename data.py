"""
Downloads and caches historical international match results.
Source: github.com/martj42/international_results — 100% free, no API key.
"""

import os
import pandas as pd
import requests
from datetime import datetime, timedelta
from config import TRAINING_YEARS

DATA_URL = "https://raw.githubusercontent.com/martj42/international_results/master/results.csv"
CACHE_FILE = "results_cache.csv"


def fetch_data(force_refresh=False) -> pd.DataFrame:
    if not force_refresh and os.path.exists(CACHE_FILE):
        age_hours = (datetime.now() - datetime.fromtimestamp(os.path.getmtime(CACHE_FILE))).total_seconds() / 3600
        if age_hours < 24:
            print(f"  Using cached data ({CACHE_FILE})")
            return _load_and_filter(pd.read_csv(CACHE_FILE))

    print("  Downloading historical match data from GitHub...")
    resp = requests.get(DATA_URL, timeout=30)
    resp.raise_for_status()

    with open(CACHE_FILE, "wb") as f:
        f.write(resp.content)

    print(f"  Downloaded {len(resp.content) // 1024}KB of match data.")
    return _load_and_filter(pd.read_csv(CACHE_FILE))


def _load_and_filter(df: pd.DataFrame) -> pd.DataFrame:
    df["date"] = pd.to_datetime(df["date"])
    cutoff = datetime.now() - timedelta(days=365 * TRAINING_YEARS)
    df = df[df["date"] >= cutoff].copy()

    # Drop matches without scores
    df = df.dropna(subset=["home_score", "away_score"])
    df["home_score"] = df["home_score"].astype(int)
    df["away_score"] = df["away_score"].astype(int)

    # Weight competitive matches higher
    competitive = {"FIFA World Cup", "FIFA World Cup qualification", "UEFA Euro",
                   "UEFA Euro qualification", "CONMEBOL Copa América",
                   "AFC Asian Cup", "CONCACAF Gold Cup"}
    df["weight"] = df["tournament"].apply(lambda t: 2.0 if t in competitive else 1.0)

    print(f"  Loaded {len(df):,} matches from the last {TRAINING_YEARS} years.")
    return df.reset_index(drop=True)
