"""
Gold Telegram Signal Bot

Strategy:
    LONG if SMA100 > SMA250 OR month in Nov/Dec/Jan/Feb
    else CASH

This script:
1) Reads existing daily gold price history from data/gold_daily.csv
2) Optionally fetches latest live spot gold price from igold24 API
3) Updates/appends today's daily row
4) Calculates the latest signal
5) Sends a Telegram alert

Not financial advice. Historical/live signals can be wrong.
"""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd
import requests
from dateutil import parser as date_parser


DEFAULT_API_URL = "https://igold24.com/api/cached-gold-prices.json"
DEFAULT_STRATEGY_NAME = "Gold Trend Seasonality Master"
SEASONAL_MONTHS = {11, 12, 1, 2}


@dataclass
class SignalResult:
    signal_date: str
    price: float
    sma100: float
    sma250: float
    trend_long: bool
    seasonal_long: bool
    signal: str
    reason: str


def env(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return value


def load_history(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(
            f"Data file not found: {path}. Add historical daily data with columns: Date,Open,High,Low,Close,Volume"
        )

    df = pd.read_csv(path)
    required = {"Date", "Close"}
    missing = required.difference(df.columns)
    if missing:
        raise ValueError(f"Missing required columns in {path}: {sorted(missing)}")

    df["Date"] = pd.to_datetime(df["Date"]).dt.date
    for col in ["Open", "High", "Low", "Close", "Volume"]:
        if col not in df.columns:
            df[col] = pd.NA
    df["Close"] = pd.to_numeric(df["Close"], errors="coerce")
    df = df.dropna(subset=["Date", "Close"]).sort_values("Date").drop_duplicates("Date", keep="last")
    return df[["Date", "Open", "High", "Low", "Close", "Volume"]]


def save_history(df: pd.DataFrame, path: Path) -> None:
    out = df.copy()
    out["Date"] = pd.to_datetime(out["Date"]).dt.strftime("%Y-%m-%d")
    path.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(path, index=False)


def parse_api_datetime(data: dict[str, Any], user_tz: str) -> datetime:
    # igold24 usually returns `updated_at` and `timezone`.
    updated_at = data.get("updated_at") or data.get("updatedAt") or data.get("time")
    api_tz = data.get("timezone") or user_tz

    if updated_at:
        dt = date_parser.parse(str(updated_at))
        if dt.tzinfo is None:
            try:
                dt = dt.replace(tzinfo=ZoneInfo(str(api_tz)))
            except Exception:
                dt = dt.replace(tzinfo=ZoneInfo(user_tz))
        return dt.astimezone(ZoneInfo(user_tz))

    return datetime.now(ZoneInfo(user_tz))


def fetch_live_price() -> tuple[float, datetime, dict[str, Any]]:
    api_url = env("API_URL", DEFAULT_API_URL)
    price_field = env("PRICE_FIELD", "world_ounce_usd")
    user_tz = env("USER_TZ", "Asia/Kolkata")

    response = requests.get(str(api_url), timeout=20)
    response.raise_for_status()
    data = response.json()

    if isinstance(data, dict) and data.get("success") is False:
        raise RuntimeError(f"API returned success=false: {data}")

    if price_field not in data:
        raise KeyError(
            f"PRICE_FIELD='{price_field}' not found in API response. Available keys: {list(data)[:30]}"
        )

    price = float(data[price_field])
    dt = parse_api_datetime(data, str(user_tz))
    return price, dt, data


def update_daily_row(df: pd.DataFrame, signal_date, price: float) -> pd.DataFrame:
    df = df.copy()
    signal_date = pd.to_datetime(signal_date).date()

    if signal_date in set(df["Date"]):
        idx = df.index[df["Date"] == signal_date][-1]
        old_open = df.at[idx, "Open"]
        old_high = df.at[idx, "High"]
        old_low = df.at[idx, "Low"]

        df.at[idx, "Open"] = old_open if pd.notna(old_open) else price
        df.at[idx, "High"] = max(float(old_high), price) if pd.notna(old_high) else price
        df.at[idx, "Low"] = min(float(old_low), price) if pd.notna(old_low) else price
        df.at[idx, "Close"] = price
    else:
        new_row = {
            "Date": signal_date,
            "Open": price,
            "High": price,
            "Low": price,
            "Close": price,
            "Volume": pd.NA,
        }
        df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)

    df = df.sort_values("Date").drop_duplicates("Date", keep="last")
    return df


def calculate_signal(df: pd.DataFrame) -> tuple[pd.DataFrame, SignalResult]:
    data = df.copy().sort_values("Date")
    data["Close"] = pd.to_numeric(data["Close"], errors="coerce")
    data = data.dropna(subset=["Close"])

    if len(data) < 250:
        raise ValueError(f"Need at least 250 daily closes. Current rows: {len(data)}")

    data["sma100"] = data["Close"].rolling(100).mean()
    data["sma250"] = data["Close"].rolling(250).mean()
    dates = pd.to_datetime(data["Date"])
    data["trend_long"] = data["sma100"] > data["sma250"]
    data["seasonal_long"] = dates.dt.month.isin(SEASONAL_MONTHS)
    data["raw_signal"] = data["trend_long"] | data["seasonal_long"]

    last = data.iloc[-1]
    signal = "LONG" if bool(last["raw_signal"]) else "CASH"

    if bool(last["trend_long"]) and bool(last["seasonal_long"]):
        reason = "Trend positive + seasonal month"
    elif bool(last["trend_long"]):
        reason = "Trend positive: SMA100 > SMA250"
    elif bool(last["seasonal_long"]):
        reason = "Seasonal month: Nov/Dec/Jan/Feb"
    else:
        reason = "Trend negative and not a seasonal month"

    result = SignalResult(
        signal_date=str(last["Date"]),
        price=float(last["Close"]),
        sma100=float(last["sma100"]),
        sma250=float(last["sma250"]),
        trend_long=bool(last["trend_long"]),
        seasonal_long=bool(last["seasonal_long"]),
        signal=signal,
        reason=reason,
    )
    return data, result


def build_message(result: SignalResult) -> str:
    strategy_name = env("STRATEGY_NAME", DEFAULT_STRATEGY_NAME)
    emoji = "🟢" if result.signal == "LONG" else "🔴"
    trend = "YES" if result.trend_long else "NO"
    seasonal = "YES" if result.seasonal_long else "NO"

    return (
        f"{emoji} Strategy: {strategy_name}\n"
        f"GOLD SIGNAL: {result.signal}\n\n"
        f"Date: {result.signal_date}\n"
        f"Price: {result.price:,.2f}\n"
        f"SMA100: {result.sma100:,.2f}\n"
        f"SMA250: {result.sma250:,.2f}\n\n"
        f"Trend condition SMA100 > SMA250: {trend}\n"
        f"Seasonal month Nov-Feb: {seasonal}\n"
        f"Reason: {result.reason}\n\n"
        "Rule: LONG if SMA100 > SMA250 OR month is Nov/Dec/Jan/Feb; otherwise CASH.\n"
        "Meaning: LONG = buy/hold gold exposure; CASH = exit/stay out, not short.\n"
        "Note: Historical system signal only, not financial advice."
    )


def send_telegram(message: str) -> None:
    token = env("TELEGRAM_BOT_TOKEN")
    chat_id = env("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        raise RuntimeError("Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID environment variable.")

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "disable_web_page_preview": True,
    }
    response = requests.post(url, json=payload, timeout=20)
    response.raise_for_status()


def should_send(result: SignalResult, log_path: Path) -> bool:
    alert_mode = env("ALERT_MODE", "always").lower()
    if alert_mode == "always":
        return True

    if not log_path.exists():
        return True

    previous = json.loads(log_path.read_text(encoding="utf-8"))
    if alert_mode == "change":
        return previous.get("signal") != result.signal

    return True


def write_log(result: SignalResult, log_path: Path, message: str) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "signal_date": result.signal_date,
        "price": result.price,
        "sma100": result.sma100,
        "sma250": result.sma250,
        "trend_long": result.trend_long,
        "seasonal_long": result.seasonal_long,
        "signal": result.signal,
        "reason": result.reason,
        "message": message,
        "created_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    log_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Gold SMA100/SMA250 + seasonality Telegram signal bot")
    parser.add_argument("--skip-fetch", action="store_true", help="Do not call live API; use latest row from CSV only")
    parser.add_argument("--no-send", action="store_true", help="Do not send Telegram message")
    parser.add_argument("--data-file", default=env("DATA_FILE", "data/gold_daily.csv"))
    parser.add_argument("--log-file", default=env("LOG_FILE", "logs/latest_signal.json"))
    args = parser.parse_args()

    data_path = Path(args.data_file)
    log_path = Path(args.log_file)

    df = load_history(data_path)

    if not args.skip_fetch:
        price, dt, _api_data = fetch_live_price()
        df = update_daily_row(df, dt.date(), price)
        save_history(df, data_path)

    _signal_df, result = calculate_signal(df)
    message = build_message(result)
    print(message)

    if not args.no_send and should_send(result, log_path):
        send_telegram(message)
        print("Telegram message sent.")
    elif not args.no_send:
        print("No Telegram message sent because ALERT_MODE=change and signal did not change.")

    write_log(result, log_path, message)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
