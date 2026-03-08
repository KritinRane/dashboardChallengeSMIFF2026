"""
Backend API: backtest requests, automatic ingestion when data is missing.
"""
import os
import time
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

try:
    from backend.database import get_session, get_missing_dates, init_db, get_engine, OHLCV
    from backend.backtest import run_constant_threshold_backtest, run_sma_crossover_backtest
except ModuleNotFoundError:
    from database import get_session, get_missing_dates, init_db, get_engine, OHLCV
    from backtest import run_constant_threshold_backtest, run_sma_crossover_backtest

app = FastAPI(title="Backtest Dashboard API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Symbol and strategy config (graders may change these)
DEFAULT_SYMBOL = "AAPL"
STRATEGY_CHOICES = ["constant_threshold", "sma_crossover"]


class BacktestRequest(BaseModel):
    start_date: str = Field(..., description="Start date YYYY-MM-DD")
    end_date: str = Field(..., description="End date YYYY-MM-DD")
    symbol: str = Field(default=DEFAULT_SYMBOL, description="Symbol to backtest")
    strategy: str = Field(default="constant_threshold", description="Strategy name")
    # Constant threshold params
    threshold: float = Field(default=150.0, description="Price threshold for entry (constant_threshold)")
    hold_bars: int = Field(default=5, ge=1, le=252, description="Bars to hold (constant_threshold)")
    # SMA crossover params
    fast_period: int = Field(default=10, ge=2, le=100, description="Fast SMA period (sma_crossover)")
    slow_period: int = Field(default=30, ge=2, le=200, description="Slow SMA period (sma_crossover)")


def run_ingester(symbol: str, start: date, end: date) -> None:
    """Call the standalone ingester script to fill missing data."""
    backend_dir = Path(__file__).resolve().parent
    script = backend_dir / "ingester.py"
    env = {**os.environ}
    env["PYTHONPATH"] = str(backend_dir) + os.pathsep + env.get("PYTHONPATH", "")
    cmd = [
        sys.executable,
        str(script),
        "--symbol", symbol,
        "--start", start.isoformat(),
        "--end", end.isoformat(),
    ]
    result = subprocess.run(cmd, cwd=str(backend_dir), check=True, capture_output=True, text=True, env=env)
    print("Ingester stdout:", result.stdout)
    print("Ingester stderr:", result.stderr)


def load_ohlcv_df(symbol: str, start: date, end: date) -> pd.DataFrame:
    """Load OHLCV from DB for symbol in [start, end] as a DataFrame."""
    engine = get_engine()
    with get_session(engine) as session:
        rows = (
            session.query(OHLCV)
            .filter(
                OHLCV.symbol == symbol,
                OHLCV.date >= start,
                OHLCV.date <= end,
            )
            .order_by(OHLCV.date)
            .all()
        )
        if not rows:
            return pd.DataFrame()
        return pd.DataFrame([{**r.to_dict(), "date": r.date} for r in rows])


@app.on_event("startup")
def startup():
    """Ensure database tables exist on startup."""
    init_db()


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.post("/api/backtest")
def run_backtest(req: BacktestRequest):
    """Run backtest for the given range and strategy. Ensures data exists by calling ingester if needed."""
    try:
        start = datetime.strptime(req.start_date, "%Y-%m-%d").date()
        end = datetime.strptime(req.end_date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format; use YYYY-MM-DD")
    if start > end:
        raise HTTPException(status_code=400, detail="start_date must be <= end_date")
    if req.strategy not in STRATEGY_CHOICES:
        raise HTTPException(status_code=400, detail=f"strategy must be one of {STRATEGY_CHOICES}")

    try:
        init_db()
        engine = get_engine()
        with get_session(engine) as session:
            missing = get_missing_dates(session, req.symbol, start, end)
        if missing:
            try:
                run_ingester(req.symbol, start, end)
                time.sleep(2)
            except subprocess.CalledProcessError as e:
                stderr = (e.stderr or "").strip() if e.stderr else ""
                raise HTTPException(
                    status_code=503,
                    detail=f"Ingester failed: {stderr or str(e)}",
                )

        df = load_ohlcv_df(req.symbol, start, end)
        if df.empty:
            raise HTTPException(status_code=404, detail="No OHLCV data in the requested range")

        if req.strategy == "constant_threshold":
            result = run_constant_threshold_backtest(df, threshold=req.threshold, hold_bars=req.hold_bars)
        else:
            result = run_sma_crossover_backtest(
                df, fast_period=req.fast_period, slow_period=req.slow_period
            )

        return result.to_dict()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Backtest error: {str(e)}")


@app.get("/api/strategies")
def list_strategies():
    """Return available strategy names and their parameters for the frontend."""
    return {
        "strategies": [
            {
                "id": "constant_threshold",
                "name": "Constant Price Threshold",
                "params": [
                    {"key": "threshold", "label": "Price threshold", "type": "number", "default": 150},
                    {"key": "hold_bars", "label": "Hold (bars)", "type": "number", "default": 5},
                ],
            },
            {
                "id": "sma_crossover",
                "name": "SMA Crossover",
                "params": [
                    {"key": "fast_period", "label": "Fast SMA period", "type": "number", "default": 10},
                    {"key": "slow_period", "label": "Slow SMA period", "type": "number", "default": 30},
                ],
            },
        ],
        "default_symbol": DEFAULT_SYMBOL,
    }


# Serve frontend static files when running in Docker (must be registered AFTER API routes)
_static_path = Path(__file__).resolve().parent / "static"
if _static_path.exists():
    app.mount("/assets", StaticFiles(directory=_static_path / "assets"), name="assets")

    @app.get("/", response_class=FileResponse)
    def index():
        return FileResponse(_static_path / "index.html")

    @app.get("/index.html", response_class=FileResponse)
    def index_html():
        return FileResponse(_static_path / "index.html")

    @app.api_route("/{path:path}", methods=["GET"], response_class=FileResponse)
    def spa_catchall(path: str):
        """Serve index.html for all non-API client-side routes."""
        return FileResponse(_static_path / "index.html")
