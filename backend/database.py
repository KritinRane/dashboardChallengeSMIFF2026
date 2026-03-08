"""
Database module: schema and session management for OHLCV price data.
Uses PostgreSQL (or SQLite for local dev) to store symbol daily bars.
"""
import os
from datetime import date
from contextlib import contextmanager
from sqlalchemy import create_engine, Column, String, Date, Float, Integer, UniqueConstraint, text
from sqlalchemy.orm import declarative_base, sessionmaker, Session

Base = declarative_base()


class OHLCV(Base):
    """Daily OHLCV bar for a symbol."""
    __tablename__ = "ohlcv"
    __table_args__ = (UniqueConstraint("symbol", "date", name="uq_ohlcv_symbol_date"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(32), nullable=False, index=True)
    date = Column(Date, nullable=False, index=True)
    open = Column(Float, nullable=False)
    high = Column(Float, nullable=False)
    low = Column(Float, nullable=False)
    close = Column(Float, nullable=False)
    volume = Column(Float, nullable=True)

    def to_dict(self):
        return {
            "date": self.date.isoformat() if self.date else None,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
        }


def get_database_url() -> str:
    """Database URL from env (Docker) or SQLite for local run without Docker."""
    return os.environ.get(
        "DATABASE_URL",
        "sqlite:///./backtest.db"  # local file in backend dir when running without Docker
    )


def get_engine():
    url = get_database_url()
    # SQLite doesn't need pool_pre_ping; PostgreSQL does
    if url.startswith("sqlite"):
        return create_engine(url, connect_args={"check_same_thread": False})
    return create_engine(url, pool_pre_ping=True)


def init_db(engine=None):
    """Create tables if they do not exist."""
    engine = engine or get_engine()
    Base.metadata.create_all(engine)


@contextmanager
def get_session(engine=None) -> Session:
    """Context manager for a single DB session."""
    engine = engine or get_engine()
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _is_weekday(d: date) -> bool:
    """Monday=0, Sunday=6; weekday is Mon–Fri."""
    return d.weekday() < 5


def get_missing_dates(session: Session, symbol: str, start: date, end: date) -> list:
    """Return list of trading weekdays in [start, end] that have no row for the given symbol."""
    from datetime import timedelta
    url = get_database_url()
    if url.startswith("sqlite"):
        # SQLite: no generate_series; use Python to build weekday range and subtract what we have
        have = set(
            row[0] for row in session.execute(
                text("SELECT date FROM ohlcv WHERE symbol = :symbol AND date >= :start AND date <= :end"),
                {"symbol": symbol, "start": start, "end": end}
            )
        )
        missing = []
        d = start
        while d <= end:
            if _is_weekday(d) and d not in have:
                missing.append(d)
            d += timedelta(days=1)
        return missing
    # PostgreSQL
    result = session.execute(
        text("""
            WITH range AS (
                SELECT generate_series(:start::date, :end::date, '1 day'::interval)::date AS d
            ),
            weekdays AS (
                SELECT d FROM range WHERE EXTRACT(DOW FROM d) BETWEEN 1 AND 5
            ),
            have AS (
                SELECT date FROM ohlcv WHERE symbol = :symbol
            )
            SELECT w.d AS missing_date
            FROM weekdays w
            LEFT JOIN have h ON w.d = h.date
            WHERE h.date IS NULL
            ORDER BY w.d
        """),
        {"symbol": symbol, "start": start, "end": end}
    )
    return [row[0] for row in result]
