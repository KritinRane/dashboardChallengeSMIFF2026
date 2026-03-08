import { useState, useEffect } from "react";

type StrategyParam = { key: string; label: string; type: string; default: number };
type Strategy = { id: string; name: string; params: StrategyParam[] };
type StrategiesResponse = { strategies: Strategy[]; default_symbol: string };

type Trade = {
  entry_date: string;
  exit_date: string;
  side: string;
  entry_price: number;
  exit_price: number;
  quantity: number;
  pnl: number;
  pnl_pct: number;
};

type BacktestResult = {
  trades: Trade[];
  total_pnl: number;
  annualized_return: number;
  max_drawdown: number;
  win_probability: number;
  num_trades: number;
  num_wins: number;
};

// Use relative /api when using Vite dev server (proxy). For direct backend access use http://localhost:8000
const API = import.meta.env.VITE_API_URL ?? "";

export default function App() {
  const [strategies, setStrategies] = useState<StrategiesResponse | null>(null);
  const [startDate, setStartDate] = useState("2024-01-01");
  const [endDate, setEndDate] = useState("2024-06-30");
  const [symbol, setSymbol] = useState("AAPL");
  const [strategyId, setStrategyId] = useState("constant_threshold");
  const [params, setParams] = useState<Record<string, number>>({});
  const [result, setResult] = useState<BacktestResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const url = `${API}/api/strategies`;
    fetch(url)
      .then((r) => {
        if (!r.ok) throw new Error(`${r.status}`);
        return r.json();
      })
      .then((data: StrategiesResponse) => {
        setStrategies(data);
        setSymbol(data.default_symbol);
        const first = data.strategies[0];
        if (first) {
          setStrategyId(first.id);
          const defaults: Record<string, number> = {};
          first.params.forEach((p) => (defaults[p.key] = p.default));
          setParams(defaults);
        }
        setError(null);
      })
      .catch(() =>
        setError(
          "Failed to load strategies. Make sure the backend is running: in a terminal run « cd backend && uvicorn main:app --reload --host 0.0.0.0 --port 8000 » then refresh."
        )
      );
  }, []);

  useEffect(() => {
    if (!strategies) return;
    const s = strategies.strategies.find((x) => x.id === strategyId);
    if (s) {
      const next: Record<string, number> = {};
      s.params.forEach((p) => (next[p.key] = params[p.key] ?? p.default));
      setParams(next);
    }
  }, [strategyId, strategies]);

  const runBacktest = async () => {
    setError(null);
    setResult(null);
    setLoading(true);
    try {
      const body: Record<string, unknown> = {
        start_date: startDate,
        end_date: endDate,
        symbol,
        strategy: strategyId,
        ...params,
      };
      const res = await fetch(`${API}/api/backtest`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        const msg = Array.isArray(data.detail) ? data.detail.map((x: { msg?: string }) => x?.msg).filter(Boolean).join("; ") : (data.detail || res.statusText || "Backtest failed");
        throw new Error(typeof msg === "string" ? msg : "Backtest failed");
      }
      setResult(data as BacktestResult);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Backtest failed");
    } finally {
      setLoading(false);
    }
  };

  const currentStrategy = strategies?.strategies.find((s) => s.id === strategyId);

  const applySample = (data: Record<string, unknown>) => {
    setError(null);
    if (typeof data.start_date === "string") setStartDate(data.start_date);
    if (typeof data.end_date === "string") setEndDate(data.end_date);
    if (typeof data.symbol === "string") setSymbol(String(data.symbol).toUpperCase());
    if (typeof data.strategy === "string") setStrategyId(data.strategy);
    if (data && typeof data === "object" && !Array.isArray(data)) {
      const p: Record<string, number> = {};
      if (typeof data.threshold === "number") p.threshold = data.threshold;
      if (typeof data.hold_bars === "number") p.hold_bars = data.hold_bars;
      if (typeof data.fast_period === "number") p.fast_period = data.fast_period;
      if (typeof data.slow_period === "number") p.slow_period = data.slow_period;
      if (Object.keys(p).length) setParams((prev) => ({ ...prev, ...p }));
    }
  };

  const loadSample = (file: string) => {
    const fallbackThreshold: Record<string, unknown> = {
      start_date: "2024-01-01",
      end_date: "2024-06-30",
      symbol: "AAPL",
      strategy: "constant_threshold",
      threshold: 185,
      hold_bars: 5,
    };
    const fallbackSma: Record<string, unknown> = {
      start_date: "2024-01-01",
      end_date: "2024-12-31",
      symbol: "AAPL",
      strategy: "sma_crossover",
      fast_period: 10,
      slow_period: 30,
    };
    const fallback = file.includes("sma") ? fallbackSma : fallbackThreshold;
    fetch(file)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error("Not found"))))
      .then((data: Record<string, unknown>) => applySample(data))
      .catch(() => {
        applySample(fallback);
      });
  };

  return (
    <div className="app">
      <header className="header">
        <h1>Backtest Dashboard</h1>
        <p className="subtitle">Run strategy backtests and view trades and metrics</p>
      </header>

      <section className="card form-card">
        <h2>Backtest parameters</h2>
        <div className="form-grid">
          <label>
            <span>Start date</span>
            <input
              type="date"
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
            />
          </label>
          <label>
            <span>End date</span>
            <input
              type="date"
              value={endDate}
              onChange={(e) => setEndDate(e.target.value)}
            />
          </label>
          <label>
            <span>Symbol</span>
            <input
              type="text"
              value={symbol}
              onChange={(e) => setSymbol(e.target.value.toUpperCase())}
              placeholder="e.g. AAPL"
            />
          </label>
          {strategies && (
            <label>
              <span>Strategy</span>
              <select
                value={strategyId}
                onChange={(e) => setStrategyId(e.target.value)}
              >
                {strategies.strategies.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.name}
                  </option>
                ))}
              </select>
            </label>
          )}
          {currentStrategy?.params.map((p) => (
            <label key={p.key}>
              <span>{p.label}</span>
              <input
                type="number"
                value={params[p.key] ?? p.default}
                onChange={(e) =>
                  setParams((prev) => ({ ...prev, [p.key]: Number(e.target.value) }))
                }
                min={p.key.includes("period") ? 2 : undefined}
              />
            </label>
          ))}
        </div>
        <div className="form-actions">
          <button
            type="button"
            className="secondary-btn"
            onClick={() => loadSample("/sample-backtest.json")}
          >
            Load sample (threshold)
          </button>
          <button
            type="button"
            className="secondary-btn"
            onClick={() => loadSample("/sample-backtest-sma.json")}
          >
            Load sample (SMA)
          </button>
          <button
            className="primary-btn"
            onClick={runBacktest}
            disabled={loading}
          >
            {loading ? "Running backtest…" : "Run backtest"}
          </button>
        </div>
      </section>

      {error && (
        <div className="card error-card">
          <strong>Error:</strong> {error}
        </div>
      )}

      {result && (
        <>
          <section className="card metrics-card">
            <h2>Metrics</h2>
            <div className="metrics-grid">
              <div className="metric">
                <span className="metric-label">Profit / Loss</span>
                <span className={`metric-value ${result.total_pnl >= 0 ? "positive" : "negative"}`}>
                  {result.total_pnl >= 0 ? "+" : ""}
                  {result.total_pnl.toFixed(2)}
                </span>
              </div>
              <div className="metric">
                <span className="metric-label">Annualized return (%)</span>
                <span className={`metric-value ${result.annualized_return >= 0 ? "positive" : "negative"}`}>
                  {result.annualized_return >= 0 ? "+" : ""}
                  {result.annualized_return.toFixed(2)}%
                </span>
              </div>
              <div className="metric">
                <span className="metric-label">Max drawdown</span>
                <span className="metric-value">{result.max_drawdown.toFixed(2)}</span>
              </div>
              <div className="metric">
                <span className="metric-label">Win probability (%)</span>
                <span className="metric-value">{result.win_probability.toFixed(1)}%</span>
              </div>
              <div className="metric">
                <span className="metric-label">Trades</span>
                <span className="metric-value">{result.num_trades}</span>
              </div>
              <div className="metric">
                <span className="metric-label">Winning trades</span>
                <span className="metric-value">{result.num_wins}</span>
              </div>
            </div>
          </section>

          <section className="card trades-card">
            <h2>Trades ({result.trades.length})</h2>
            <div className="table-wrap">
              <table className="trades-table">
                <thead>
                  <tr>
                    <th>Entry date</th>
                    <th>Exit date</th>
                    <th>Side</th>
                    <th>Entry price</th>
                    <th>Exit price</th>
                    <th>P/L</th>
                    <th>P/L %</th>
                  </tr>
                </thead>
                <tbody>
                  {result.trades.map((t, i) => (
                    <tr key={i}>
                      <td>{t.entry_date}</td>
                      <td>{t.exit_date}</td>
                      <td>{t.side}</td>
                      <td className="mono">{t.entry_price.toFixed(2)}</td>
                      <td className="mono">{t.exit_price.toFixed(2)}</td>
                      <td className={t.pnl >= 0 ? "positive" : "negative"}>
                        {t.pnl >= 0 ? "+" : ""}
                        {t.pnl.toFixed(2)}
                      </td>
                      <td className={t.pnl_pct >= 0 ? "positive" : "negative"}>
                        {t.pnl_pct >= 0 ? "+" : ""}
                        {t.pnl_pct.toFixed(2)}%
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {result.trades.length === 0 && (
              <p className="muted">No trades generated for this period and strategy.</p>
            )}
          </section>
        </>
      )}

      <footer className="footer">
        <p>SSMIF Quant — Backtest Dashboard</p>
      </footer>
    </div>
  );
}
