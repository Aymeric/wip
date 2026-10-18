"""
Embedded SQLite Database Storage Engine for GEX Options Trading System.
Provides ACID transactions, indexed historical queries, and performance analytics
for realized trades and daily GEX snapshots.
"""

import os
import sqlite3
from typing import Dict, List, Optional, Any
from pathlib import Path

DEFAULT_DB_PATH = os.path.join("data", "trades.db")


def init_db(db_path: Optional[str] = None) -> sqlite3.Connection:
    """Initializes the SQLite database with required tables and indexes."""
    path = db_path or DEFAULT_DB_PATH
    dir_name = os.path.dirname(path)
    if dir_name:
        os.makedirs(dir_name, exist_ok=True)

    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    with conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS trades (
                trade_id TEXT PRIMARY KEY,
                account TEXT,
                symbol TEXT NOT NULL,
                asset_type TEXT NOT NULL,
                quantity REAL NOT NULL,
                entry_price REAL NOT NULL,
                exit_price REAL NOT NULL,
                realized_pnl REAL NOT NULL,
                realized_pnl_pct REAL NOT NULL,
                opened_at TEXT,
                closed_at TEXT,
                holding_days INTEGER DEFAULT 0,
                exit_reason TEXT DEFAULT 'MANUAL',
                target_mode TEXT DEFAULT 'T1'
            );
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_trades_account ON trades (account);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_trades_symbol ON trades (symbol);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_trades_closed_at ON trades (closed_at);")

        conn.execute("""
            CREATE TABLE IF NOT EXISTS gex_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                session_date TEXT NOT NULL,
                spot REAL NOT NULL,
                ptrans REAL,
                ntrans REAL,
                call_wall REAL,
                put_wall REAL,
                total_call_gex REAL,
                total_put_gex REAL,
                net_gex REAL,
                UNIQUE(symbol, session_date)
            );
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_gex_symbol_date ON gex_snapshots (symbol, session_date);")

    return conn


def upsert_trade(
    trade_id: str,
    symbol: str,
    asset_type: str,
    quantity: float,
    entry_price: float,
    exit_price: float,
    realized_pnl: float,
    realized_pnl_pct: float,
    account: Optional[str] = None,
    opened_at: Optional[str] = None,
    closed_at: Optional[str] = None,
    holding_days: int = 0,
    exit_reason: str = "MANUAL",
    target_mode: str = "T1",
    db_path: Optional[str] = None,
) -> None:
    """Inserts or updates a trade record in the embedded database."""
    conn = init_db(db_path)
    with conn:
        conn.execute(
            """
            INSERT INTO trades (
                trade_id, account, symbol, asset_type, quantity,
                entry_price, exit_price, realized_pnl, realized_pnl_pct,
                opened_at, closed_at, holding_days, exit_reason, target_mode
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(trade_id) DO UPDATE SET
                account=excluded.account,
                exit_price=excluded.exit_price,
                realized_pnl=excluded.realized_pnl,
                realized_pnl_pct=excluded.realized_pnl_pct,
                closed_at=excluded.closed_at,
                holding_days=excluded.holding_days,
                exit_reason=excluded.exit_reason;
            """,
            (
                trade_id, account, symbol, asset_type, quantity,
                entry_price, exit_price, realized_pnl, realized_pnl_pct,
                opened_at, closed_at, holding_days, exit_reason, target_mode
            ),
        )
    conn.close()


def query_trade_metrics(account: Optional[str] = None, db_path: Optional[str] = None) -> Dict[str, Any]:
    """Computes quantitative trade journal metrics from the database."""
    conn = init_db(db_path)
    cur = conn.cursor()

    query = "SELECT realized_pnl, realized_pnl_pct, holding_days FROM trades"
    params = []
    if account:
        query += " WHERE account = ?"
        params.append(account)

    cur.execute(query, params)
    rows = cur.fetchall()
    conn.close()

    total_trades = len(rows)
    if total_trades == 0:
        return {
            "total_trades": 0,
            "win_rate": 0.0,
            "profit_factor": 0.0,
            "total_realized_pnl": 0.0,
            "avg_win": 0.0,
            "avg_loss": 0.0,
            "avg_holding_days": 0.0,
        }

    wins = [r["realized_pnl"] for r in rows if r["realized_pnl"] > 0]
    losses = [abs(r["realized_pnl"]) for r in rows if r["realized_pnl"] < 0]
    holding = [r["holding_days"] for r in rows if r["holding_days"] is not None]

    win_count = len(wins)
    win_rate = (win_count / total_trades) * 100.0

    total_win_dollars = sum(wins)
    total_loss_dollars = sum(losses)
    profit_factor = (total_win_dollars / total_loss_dollars) if total_loss_dollars > 0 else (999.0 if total_win_dollars > 0 else 0.0)

    avg_win = total_win_dollars / win_count if win_count > 0 else 0.0
    avg_loss = total_loss_dollars / len(losses) if losses else 0.0
    avg_holding = sum(holding) / len(holding) if holding else 0.0

    total_pnl = sum(r["realized_pnl"] for r in rows)

    return {
        "total_trades": total_trades,
        "wins": win_count,
        "losses": len(losses),
        "win_rate": round(win_rate, 2),
        "profit_factor": round(profit_factor, 2),
        "total_realized_pnl": round(total_pnl, 2),
        "avg_win": round(avg_win, 2),
        "avg_loss": round(avg_loss, 2),
        "avg_holding_days": round(avg_holding, 1),
    }


def sync_closed_positions_to_db(
    closed_data: Dict[str, Any],
    account: Optional[str] = None,
    db_path: Optional[str] = None,
) -> int:
    """Synchronizes closed positions dict (options and stocks) into SQLite."""
    from datetime import date

    synced_count = 0
    closed_options = closed_data.get("closed_options", []) or []
    closed_stocks = closed_data.get("closed_stocks", []) or []

    for idx, opt in enumerate(closed_options):
        symbol = opt.get("Underlier") or opt.get("Ticker") or "UNKNOWN"
        opt_id = opt.get("Option ID") or opt.get("id") or f"{account or 'default'}_opt_{symbol}_{idx}"
        strike = opt.get("Strike", "")
        exp = opt.get("Expiration", "")
        opened_at = opt.get("Entry Date")
        closed_at = opt.get("Close Date")

        qty = 1.0
        if "Quantity" in opt:
            try:
                qty = float(opt["Quantity"])
            except (ValueError, TypeError):
                qty = 1.0

        entry_px = float(opt.get("Purchase Premium", 0.0) or 0.0)
        exit_px = float(opt.get("Close Premium", 0.0) or 0.0)
        pnl = float(opt.get("Realized P&L ($)", 0.0) or 0.0)
        pnl_pct = float(opt.get("Realized P&L (%)", 0.0) or 0.0)

        holding = 0
        if opened_at and closed_at:
            try:
                holding = max((date.fromisoformat(closed_at) - date.fromisoformat(opened_at)).days + 1, 1)
            except Exception:
                pass

        exit_reason = opt.get("Close Reason") or opt.get("Exit Reason") or opt.get("Rule State") or "MANUAL"
        target_mode = opt.get("Target Mode", "T1")

        trade_account = account or opt.get("Account") or ""

        upsert_trade(
            trade_id=str(opt_id),
            symbol=str(symbol).upper(),
            asset_type="OPTION",
            quantity=qty,
            entry_price=entry_px,
            exit_price=exit_px,
            realized_pnl=pnl,
            realized_pnl_pct=pnl_pct,
            account=trade_account,
            opened_at=opened_at,
            closed_at=closed_at,
            holding_days=holding,
            exit_reason=exit_reason,
            target_mode=target_mode,
            db_path=db_path,
        )
        synced_count += 1

    for idx, stk in enumerate(closed_stocks):
        symbol = stk.get("Ticker") or "UNKNOWN"
        trade_id = stk.get("Trade ID") or f"{account or 'default'}_stk_{symbol}_{idx}"
        opened_at = stk.get("Entry Date")
        closed_at = stk.get("Close Date")

        shares = float(stk.get("Shares", 0.0) or 0.0)
        buy_px = float(stk.get("Average Buy Price", 0.0) or 0.0)
        close_px = float(stk.get("Close Price", 0.0) or 0.0)
        pnl = float(stk.get("Realized P&L ($)", 0.0) or 0.0)
        pnl_pct = float(stk.get("Realized P&L (%)", 0.0) or 0.0)

        holding = 0
        if opened_at and closed_at:
            try:
                holding = max((date.fromisoformat(closed_at) - date.fromisoformat(opened_at)).days + 1, 1)
            except Exception:
                pass

        exit_reason = stk.get("Close Reason") or stk.get("Exit Reason") or "MANUAL"
        trade_account = account or stk.get("Account") or ""

        upsert_trade(
            trade_id=str(trade_id),
            symbol=str(symbol).upper(),
            asset_type="STOCK",
            quantity=shares,
            entry_price=buy_px,
            exit_price=close_px,
            realized_pnl=pnl,
            realized_pnl_pct=pnl_pct,
            account=trade_account,
            opened_at=opened_at,
            closed_at=closed_at,
            holding_days=holding,
            exit_reason=exit_reason,
            target_mode="T1",
            db_path=db_path,
        )
        synced_count += 1

    return synced_count


def save_gex_snapshot(
    symbol: str,
    session_date: str,
    spot: float,
    ptrans: Optional[float] = None,
    ntrans: Optional[float] = None,
    call_wall: Optional[float] = None,
    put_wall: Optional[float] = None,
    total_call_gex: Optional[float] = None,
    total_put_gex: Optional[float] = None,
    net_gex: Optional[float] = None,
    db_path: Optional[str] = None,
) -> None:
    """Saves or updates a daily GEX profile snapshot for an underlier in SQLite."""
    conn = init_db(db_path)
    with conn:
        conn.execute(
            """
            INSERT INTO gex_snapshots (
                symbol, session_date, spot, ptrans, ntrans,
                call_wall, put_wall, total_call_gex, total_put_gex, net_gex
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(symbol, session_date) DO UPDATE SET
                spot=excluded.spot,
                ptrans=excluded.ptrans,
                ntrans=excluded.ntrans,
                call_wall=excluded.call_wall,
                put_wall=excluded.put_wall,
                total_call_gex=excluded.total_call_gex,
                total_put_gex=excluded.total_put_gex,
                net_gex=excluded.net_gex;
            """,
            (
                symbol.upper(), session_date, spot, ptrans, ntrans,
                call_wall, put_wall, total_call_gex, total_put_gex, net_gex
            ),
        )
    conn.close()


def query_latest_gex_snapshot(symbol: str, db_path: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Fetches the latest GEX snapshot for a given underlier symbol."""
    conn = init_db(db_path)
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM gex_snapshots WHERE symbol = ? ORDER BY session_date DESC LIMIT 1",
        (symbol.upper(),),
    )
    row = cur.fetchone()
    conn.close()
    if row is None:
        return None
    return dict(row)

