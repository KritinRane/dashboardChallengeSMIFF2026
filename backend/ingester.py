#!/usr/bin/env python3
"""
Standalone ingester script: fetches OHLCV data for configured symbol(s) and stores in the database.
Can be run by itself (e.g. `python ingester.py [--symbol AAPL] [--start 2024-01-01] [--end 2024-12-31]`)
or invoked by the backend when backtest detects missing data.
"""
import argparse
import sys
from datetime import date, datetime, timedelta
import pandas as pd
import yfinance as yf
from sqlalchemy import create_engine
from database import get_database_url, init_db, get_session, OHLCV, get_engine


# Default symbol used for the challenge (single symbol required; more are allowed).
DEFAULT_SYMBOL = "AAPL"


def fetch_ohlcv(symbol: str, start: date, end: date) -> pd.DataFrame:
    """Download OHLCV from yfinance for the given symbol and date range."""
    start_str = start.isoformat()
    end_str = end.isoformat()
    ticker = yf.Ticker(symbol)
    df = ticker.history(start=start_str, end=end_str, auto_adjust=True)
    if df.empty:
        return df
    df = df.reset_index()
    df["Date"] = pd.to_datetime(df["Date"]).dt.date
    df = df.rename(columns={
        "Date": "date",
        "Open": "open",
        "High": "high",
        "Low": "low",
        "Close": "close",
        "Volume": "volume",
    })
    return df[["date", "open", "high", "low", "close", "volume"]]


def ingest_range(symbol: str, start: date, end: date, engine=None) -> int:
    """
    Fetch data for [start, end] and upsert into the database.
    Returns the number of rows inserted/updated.
    """
    engine = engine or get_engine()
    init_db(engine)
    df = fetch_ohlcv(symbol, start, end)
    if df.empty:
        return 0
    df["symbol"] = symbol
    with get_session(engine) as session:
        for _, row in df.iterrows():
            rec = session.query(OHLCV).filter(
                OHLCV.symbol == symbol,
                OHLCV.date == row["date"]
            ).first()
            if rec:
                rec.open = float(row["open"])
                rec.high = float(row["high"])
                rec.low = float(row["low"])
                rec.close = float(row["close"])
                rec.volume = float(row["volume"]) if pd.notna(row["volume"]) else None
            else:
                session.add(OHLCV(
                    symbol=symbol,
                    date=row["date"],
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=float(row["volume"]) if pd.notna(row["volume"]) else None,
                ))
        session.commit()
    return len(df)


def main():
    parser = argparse.ArgumentParser(description="Ingest OHLCV data into the backtest database.")
    parser.add_argument("--symbol", default=DEFAULT_SYMBOL, help="Symbol to ingest (e.g. AAPL)")
    parser.add_argument("--start", type=str, help="Start date YYYY-MM-DD (default: 1 year ago)")
    parser.add_argument("--end", type=str, help="End date YYYY-MM-DD (default: today)")
    args = parser.parse_args()

    end = date.today()
    start = end - timedelta(days=365)
    if args.start:
        start = datetime.strptime(args.start, "%Y-%m-%d").date()
    if args.end:
        end = datetime.strptime(args.end, "%Y-%m-%d").date()
    if start > end:
        print("Error: start must be <= end", file=sys.stderr)
        sys.exit(1)

    try:
        n = ingest_range(args.symbol, start, end)
        print(f"Ingested {n} rows for {args.symbol} from {start} to {end}")
    except Exception as e:
        print(f"Ingest failed: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
