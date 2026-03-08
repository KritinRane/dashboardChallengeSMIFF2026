# Backtest Dashboard — SSMIF Quant Submission

A full-stack web service that visualizes backtest results of trading algorithms. It includes a **database**, a **standalone ingester script**, a **backend** that runs backtests (and calls the ingester when data is missing), and a **frontend** to submit backtest requests and view trades and metrics.

## Components

| Component | Description |
|-----------|-------------|
| **Database** | PostgreSQL stores daily OHLCV bars per symbol. |
| **Ingester** | Standalone Python script that fetches data (via yfinance) and writes to the DB. Can be run by itself or invoked by the backend when a backtest needs missing dates. |
| **Backend** | FastAPI server: runs backtests for the selected strategy and date range, returns list of trades plus P/L, annualized return, max drawdown, and win probability. |
| **Frontend** | React SPA: start/end date, symbol, strategy and parameters; displays every trade and the required metrics. |

## Trading Strategies

Two strategies are implemented (graders may change or add more in code):

### 1. Constant Price Threshold (default)

- **Logic**: Go long when the close price crosses from **below** to **above** a fixed threshold. Close the position after a fixed number of bars (or at end of data).
- **Parameters**:
  - `threshold`: price level that triggers entry (e.g. 150).
  - `hold_bars`: number of bars to hold before closing (e.g. 5).
- **Use case**: Simple, reproducible, and easy to debug; good for verifying the pipeline.

### 2. SMA Crossover

- **Logic**: Go long when the fast simple moving average crosses **above** the slow SMA; close when the fast crosses **below** the slow (or at end of data).
- **Parameters**:
  - `fast_period`: fast SMA period (e.g. 10).
  - `slow_period`: slow SMA period (e.g. 30).

**Symbol**: The default symbol is **AAPL**. It can be changed in the frontend or in the backend constant `DEFAULT_SYMBOL` / `ingester.py` `DEFAULT_SYMBOL`.

## View the product now (no Docker)

From the project root (folder containing this README):

**Terminal 1 — backend** (uses SQLite by default; no PostgreSQL needed):
```bash
pip install -r backend/requirements.txt
cd backend && uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

**Terminal 2 — frontend**:
```bash
cd frontend && npm install && npm run dev
```

Open **http://localhost:5173** in your browser. Either click **Load sample values** to fill the form from `frontend/public/sample-backtest.json`, or set dates (e.g. 2024-01-01 to 2024-06-30), symbol (e.g. AAPL), strategy and params, then click **Run backtest**. The first run may take a moment while the backend fetches data. You can edit the sample file or use `sample-backtest-sma.json` for an SMA crossover example.

(To use Docker later, run `docker compose up --build` and open http://localhost:8000.)

## Reproducing a backtest

**If you get "Permission denied" when running `cd`:** Open this project folder in your editor (e.g. File → Open Folder → `SMIFFSubmission2026`) and use the integrated terminal; it will start in the project root so you don’t need to `cd` there. You can also run commands using the full path to the project.

1. **Using Docker (recommended)**  
   - From the project root (the folder that contains this README and `docker-compose.yml`):
     ```bash
     docker compose up --build
     ```
   - Open http://localhost:8000  
   - Set **Start date** (e.g. `2024-01-01`), **End date** (e.g. `2024-06-30`), **Symbol** (e.g. `AAPL`), **Strategy** (e.g. Constant Price Threshold), and the strategy parameters (e.g. threshold `150`, hold bars `5`).  
   - Click **Run backtest**.  
   - If data for the range is missing, the backend will run the ingester for that range and then run the backtest. Results show all trades and the metrics (P/L, annualized return, max drawdown, win probability).

2. **Without Docker (local dev)**  
   - **Database**: By default the app uses **SQLite** (file `backend/backtest.db`), so no PostgreSQL is required. To use PostgreSQL instead, set `DATABASE_URL`.
   - **Backend**: From project root, or from `backend/`:
     ```bash
     pip install -r backend/requirements.txt
     cd backend && uvicorn main:app --reload --host 0.0.0.0 --port 8000
     ```
   - **Frontend** (separate terminal):
     ```bash
     cd frontend && npm install && npm run dev
     ```
     Open http://localhost:5173 (Vite proxies `/api` to the backend).
   - **Ingester (optional)** to pre-fill data: from `backend/`, run `python ingester.py --symbol AAPL --start 2024-01-01 --end 2024-12-31`.
     Use the frontend URL (e.g. http://localhost:5173); it will proxy `/api` to the backend.

To **reproduce the same numbers**: use the same symbol, date range, and strategy parameters in the UI (or same request body to `POST /api/backtest`). The backtest is deterministic given the same OHLCV data.

## Deployment

- **Docker**: Use the provided `Dockerfile` and `docker-compose.yml`.  
  - Build and run:
    ```bash
    docker compose up --build
    ```
  - The app listens on port **8000**; the frontend is served at `/` and the API at `/api`.  
  - The compose file starts a PostgreSQL service; the app uses it via `DATABASE_URL` (set in `docker-compose.yml`).

- **Standalone Dockerfile**: The `Dockerfile` builds the frontend and runs the backend in one image. It does **not** start PostgreSQL; you must provide a running Postgres instance and set `DATABASE_URL` when running the container (e.g. link to a DB container or use a managed DB).

## Ingester behavior

- **Standalone**: Run from the repo root or `backend` directory:
  ```bash
  python backend/ingester.py [--symbol AAPL] [--start YYYY-MM-DD] [--end YYYY-MM-DD]
  ```
  Defaults: symbol `AAPL`, start = 1 year ago, end = today.

- **Called by backend**: When you submit a backtest and the database is missing any **trading weekdays** in the requested range, the backend runs the ingester for that symbol and date range automatically before running the backtest. Market holidays (weekdays with no trading) are handled gracefully — only days where yfinance returns data are stored.

## API summary

- `GET /api/health` — Health check.  
- `GET /api/strategies` — List strategies and their parameters (for the frontend form).  
- `POST /api/backtest` — Body: `start_date`, `end_date`, `symbol`, `strategy`, and strategy-specific params. Returns trades list and metrics (total_pnl, annualized_return, max_drawdown, win_probability, etc.).

## Tech stack

- **DB**: PostgreSQL (with SQLAlchemy).  
- **Backend**: Python 3.12, FastAPI, pandas, yfinance.  
- **Frontend**: React 18, TypeScript, Vite.  
- **Deploy**: Docker + docker-compose.

## Conventions

- Backend: FastAPI project layout; `backend/` holds `main.py`, `database.py`, `backtest.py`, `ingester.py`. Strategy and default symbol are centralized so graders can change them in one place.  
- Database: Single `ohlcv` table; unique on `(symbol, date)`.  
- Code is documented with docstrings and inline comments where useful.
