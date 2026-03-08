"""
Backtest engine: runs a configurable trading strategy over OHLCV data and computes
trades list and metrics (P/L, annualized return, max drawdown, win probability).
"""
from dataclasses import dataclass, field
from datetime import date
from typing import List, Optional

import pandas as pd


@dataclass
class Trade:
    """Single trade: entry and exit."""
    entry_date: date
    exit_date: date
    side: str  # "long" or "short"
    entry_price: float
    exit_price: float
    quantity: float
    pnl: float
    pnl_pct: float

    def to_dict(self):
        return {
            "entry_date": self.entry_date.isoformat(),
            "exit_date": self.exit_date.isoformat(),
            "side": self.side,
            "entry_price": round(self.entry_price, 4),
            "exit_price": round(self.exit_price, 4),
            "quantity": self.quantity,
            "pnl": round(self.pnl, 4),
            "pnl_pct": round(self.pnl_pct, 4),
        }


@dataclass
class BacktestResult:
    """Full backtest output for the API."""
    trades: List[Trade] = field(default_factory=list)
    total_pnl: float = 0.0
    annualized_return: float = 0.0
    max_drawdown: float = 0.0
    win_probability: float = 0.0
    num_trades: int = 0
    num_wins: int = 0

    def to_dict(self):
        return {
            "trades": [t.to_dict() for t in self.trades],
            "total_pnl": round(self.total_pnl, 4),
            "annualized_return": round(self.annualized_return, 4),
            "max_drawdown": round(self.max_drawdown, 4),
            "win_probability": round(self.win_probability, 4),
            "num_trades": self.num_trades,
            "num_wins": self.num_wins,
        }


def run_constant_threshold_backtest(
    df: pd.DataFrame,
    threshold: float,
    hold_bars: int,
) -> BacktestResult:
    """
    Constant price threshold strategy (as in the challenge description):
    - Go long when price crosses from below to above `threshold`.
    - Close the trade after `hold_bars` bars (or at end of data).
    """
    df = df.sort_values("date").reset_index(drop=True)
    if "close" not in df.columns or len(df) < 2:
        return BacktestResult()

    trades: List[Trade] = []
    position: Optional[dict] = None  # { "entry_idx", "entry_price", "entry_date" }

    for i in range(1, len(df)):
        prev_close = df.iloc[i - 1]["close"]
        curr_close = df.iloc[i]["close"]
        curr_date = df.iloc[i]["date"]

        # Close existing position if hold_bars reached
        if position is not None:
            bars_held = i - position["entry_idx"]
            if bars_held >= hold_bars:
                t = Trade(
                    entry_date=position["entry_date"],
                    exit_date=curr_date,
                    side="long",
                    entry_price=position["entry_price"],
                    exit_price=curr_close,
                    quantity=1.0,
                    pnl=curr_close - position["entry_price"],
                    pnl_pct=100.0 * (curr_close - position["entry_price"]) / position["entry_price"],
                )
                trades.append(t)
                position = None

        # Entry: cross from below to above threshold
        if position is None and prev_close < threshold <= curr_close:
            position = {
                "entry_idx": i,
                "entry_price": curr_close,
                "entry_date": curr_date,
            }

    # Close any remaining position at end
    if position is not None and len(df) > 0:
        last = df.iloc[-1]
        t = Trade(
            entry_date=position["entry_date"],
            exit_date=last["date"],
            side="long",
            entry_price=position["entry_price"],
            exit_price=last["close"],
            quantity=1.0,
            pnl=last["close"] - position["entry_price"],
            pnl_pct=100.0 * (last["close"] - position["entry_price"]) / position["entry_price"],
        )
        trades.append(t)

    return _metrics_from_trades(trades, df)


def run_sma_crossover_backtest(
    df: pd.DataFrame,
    fast_period: int,
    slow_period: int,
) -> BacktestResult:
    """
    Simple moving average crossover: long when fast SMA crosses above slow SMA,
    close when fast crosses below slow (or hold until crossover).
    """
    df = df.sort_values("date").reset_index(drop=True).copy()
    if len(df) < slow_period + 1:
        return BacktestResult()

    df["sma_fast"] = df["close"].rolling(fast_period, min_periods=fast_period).mean()
    df["sma_slow"] = df["close"].rolling(slow_period, min_periods=slow_period).mean()
    df["prev_fast"] = df["sma_fast"].shift(1)
    df["prev_slow"] = df["sma_slow"].shift(1)

    trades: List[Trade] = []
    position: Optional[dict] = None

    for i in range(slow_period, len(df)):
        row = df.iloc[i]
        prev_fast, prev_slow = row["prev_fast"], row["prev_slow"]
        curr_fast, curr_slow = row["sma_fast"], row["sma_slow"]
        curr_date = row["date"]
        curr_close = row["close"]

        if position is not None:
            # Close when fast crosses below slow
            if prev_fast >= prev_slow and curr_fast < curr_slow:
                t = Trade(
                    entry_date=position["entry_date"],
                    exit_date=curr_date,
                    side="long",
                    entry_price=position["entry_price"],
                    exit_price=curr_close,
                    quantity=1.0,
                    pnl=curr_close - position["entry_price"],
                    pnl_pct=100.0 * (curr_close - position["entry_price"]) / position["entry_price"],
                )
                trades.append(t)
                position = None

        if position is None and prev_fast is not None and prev_slow is not None:
            if prev_fast <= prev_slow and curr_fast > curr_slow:
                position = {"entry_date": curr_date, "entry_price": curr_close}

    if position is not None:
        last = df.iloc[-1]
        t = Trade(
            entry_date=position["entry_date"],
            exit_date=last["date"],
            side="long",
            entry_price=position["entry_price"],
            exit_price=last["close"],
            quantity=1.0,
            pnl=last["close"] - position["entry_price"],
            pnl_pct=100.0 * (last["close"] - position["entry_price"]) / position["entry_price"],
        )
        trades.append(t)

    return _metrics_from_trades(trades, df)


def _metrics_from_trades(trades: List[Trade], df: pd.DataFrame) -> BacktestResult:
    """Compute total P/L, annualized return, max drawdown, win probability."""
    total_pnl = sum(t.pnl for t in trades)
    num_trades = len(trades)
    num_wins = sum(1 for t in trades if t.pnl > 0)
    win_probability = (num_wins / num_trades * 100.0) if num_trades else 0.0

    if df.empty or "date" not in df.columns:
        return BacktestResult(
            trades=trades,
            total_pnl=total_pnl,
            annualized_return=0.0,
            max_drawdown=0.0,
            win_probability=win_probability,
            num_trades=num_trades,
            num_wins=num_wins,
        )

    # Cumulative P/L curve (by exit date) for drawdown
    dates = sorted(set(t.exit_date for t in trades))
    if not dates:
        return BacktestResult(
            trades=trades,
            total_pnl=total_pnl,
            annualized_return=0.0,
            max_drawdown=0.0,
            win_probability=win_probability,
            num_trades=num_trades,
            num_wins=num_wins,
        )

    cum_pnl = 0.0
    peak = 0.0
    max_dd = 0.0
    for t in trades:
        cum_pnl += t.pnl
        peak = max(peak, cum_pnl)
        max_dd = min(max_dd, cum_pnl - peak)

    # Annualized return: assume initial capital = first close * 1, so return = total_pnl / (first_close)
    first_close = df["close"].iloc[0]
    start_date = df["date"].min()
    end_date = df["date"].max()
    days = (end_date - start_date).days if hasattr(end_date - start_date, "days") else 1
    years = max(days / 365.25, 1 / 365.25)
    if first_close and first_close > 0:
        total_return_pct = 100.0 * total_pnl / first_close
        annualized_return = total_return_pct / years
    else:
        annualized_return = 0.0

    return BacktestResult(
        trades=trades,
        total_pnl=total_pnl,
        annualized_return=annualized_return,
        max_drawdown=abs(max_dd),
        win_probability=win_probability,
        num_trades=num_trades,
        num_wins=num_wins,
    )
