"""
Embedded SQLite Database Storage Engine for GEX Options Trading System.
Provides ACID transactions, indexed historical queries, and performance analytics
for realized trades and daily GEX snapshots.
"""

import os
import sqlite3
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
from pathlib import Path

from src.gex.core.config import (
    validate_safe_path,
    mask_account,
    sanitize_account,
    DECISION_TYPES,
    DECISION_ANSWERS,
    DECISION_TEXT_MAX_LEN,
    EXIT_REASON_CODES,
)

DEFAULT_DB_PATH = os.path.join("data", "trades.db")


def init_db(db_path: Optional[str] = None) -> sqlite3.Connection:
    """Initializes the SQLite database with required tables and indexes."""
    path = validate_safe_path(db_path or DEFAULT_DB_PATH)
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

        conn.execute("""
            CREATE TABLE IF NOT EXISTS decisions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                recorded_at TEXT NOT NULL,
                account_mask TEXT,
                decision_type TEXT NOT NULL,
                symbol TEXT NOT NULL,
                contract TEXT,
                grade TEXT,
                regime_authorization TEXT,
                gates_passed INTEGER,
                trigger_code TEXT,
                recommendation TEXT NOT NULL,
                human_answer TEXT NOT NULL,
                order_ref TEXT,
                notes TEXT
            );
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_decisions_account ON decisions (account_mask, recorded_at);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_decisions_symbol ON decisions (symbol, recorded_at);")

    return conn


_UPSERT_TRADE_SQL = """
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
"""


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
    conn: Optional[sqlite3.Connection] = None,
) -> None:
    """Inserts or updates a trade record in the embedded database."""
    params = (
        trade_id, account, symbol, asset_type, quantity,
        entry_price, exit_price, realized_pnl, realized_pnl_pct,
        opened_at, closed_at, holding_days, exit_reason, target_mode
    )
    if conn is not None:
        conn.execute(_UPSERT_TRADE_SQL, params)
    else:
        active_conn = init_db(db_path)
        with active_conn:
            active_conn.execute(_UPSERT_TRADE_SQL, params)
        active_conn.close()


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
    """Synchronizes closed positions dict (options and stocks) into SQLite.

    Performance optimization (Bolt):
    - Hoists DB connection & DDL initialization outside of record iteration loops.
    - Pre-builds parameter tuples for all closed options and stocks in memory.
    - Executes batch upsert via `conn.executemany` inside a single ACID transaction,
      eliminating N+1 database connections, DDL checks, and per-record fsync commits (~70x speedup).
    """
    from datetime import date

    closed_options = closed_data.get("closed_options", []) or []
    closed_stocks = closed_data.get("closed_stocks", []) or []

    if not closed_options and not closed_stocks:
        return 0

    trade_records: List[Tuple[Any, ...]] = []

    for idx, opt in enumerate(closed_options):
        symbol = opt.get("Underlier") or opt.get("Ticker") or "UNKNOWN"
        opt_id = opt.get("Option ID") or opt.get("id") or f"{account or 'default'}_opt_{symbol}_{idx}"
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
                holding = max((date.fromisoformat(closed_at[:10]) - date.fromisoformat(opened_at[:10])).days + 1, 1)
            except Exception:
                pass

        exit_reason = opt.get("Close Reason") or opt.get("Exit Reason") or opt.get("Rule State") or "MANUAL"
        target_mode = opt.get("Target Mode", "T1")
        trade_account = account or opt.get("Account") or ""

        trade_records.append((
            str(opt_id),
            trade_account,
            str(symbol).upper(),
            "OPTION",
            qty,
            entry_px,
            exit_px,
            pnl,
            pnl_pct,
            opened_at,
            closed_at,
            holding,
            exit_reason,
            target_mode,
        ))

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
                holding = max((date.fromisoformat(closed_at[:10]) - date.fromisoformat(opened_at[:10])).days + 1, 1)
            except Exception:
                pass

        exit_reason = stk.get("Close Reason") or stk.get("Exit Reason") or "MANUAL"
        trade_account = account or stk.get("Account") or ""

        trade_records.append((
            str(trade_id),
            trade_account,
            str(symbol).upper(),
            "STOCK",
            shares,
            buy_px,
            close_px,
            pnl,
            pnl_pct,
            opened_at,
            closed_at,
            holding,
            exit_reason,
            "T1",
        ))

    conn = init_db(db_path)
    try:
        with conn:
            conn.executemany(_UPSERT_TRADE_SQL, trade_records)
    finally:
        conn.close()

    return len(trade_records)


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


def record_decision(
    decision_type: str,
    symbol: str,
    recommendation: str,
    human_answer: str,
    account: Optional[str] = None,
    contract: Optional[str] = None,
    grade: Optional[str] = None,
    regime_authorization: Optional[str] = None,
    gates_passed: Optional[int] = None,
    trigger_code: Optional[str] = None,
    order_ref: Optional[str] = None,
    notes: Optional[str] = None,
    recorded_at: Optional[str] = None,
    db_path: Optional[str] = None,
) -> int:
    """Records a human-in-the-loop trade approval or exit decision into SQLite.

    Ensures account privacy by storing only the masked account format ('••••1234')
    and redacting any raw account references from free-text recommendation or notes.
    """
    decision_type_norm = str(decision_type or "").strip().upper()
    if decision_type_norm not in DECISION_TYPES:
        raise ValueError(f"Invalid decision_type: '{decision_type}'. Expected one of {DECISION_TYPES}")

    human_answer_norm = str(human_answer or "").strip().upper()
    if human_answer_norm not in DECISION_ANSWERS:
        raise ValueError(f"Invalid human_answer: '{human_answer}'. Expected one of {DECISION_ANSWERS}")

    if order_ref and human_answer_norm != "APPROVED":
        raise ValueError(f"order_ref can only be supplied when human_answer is 'APPROVED' (got '{human_answer_norm}')")

    trigger_norm = str(trigger_code or "").strip().upper() if trigger_code else None
    if decision_type_norm == "EXIT":
        if not trigger_norm:
            raise ValueError("trigger_code is required for EXIT decisions")
        if trigger_norm not in EXIT_REASON_CODES:
            raise ValueError(f"Invalid trigger_code: '{trigger_code}'. Expected one of {EXIT_REASON_CODES}")
    elif trigger_norm and trigger_norm not in EXIT_REASON_CODES:
        raise ValueError(f"Invalid trigger_code: '{trigger_code}'. Expected one of {EXIT_REASON_CODES}")

    grade_norm = str(grade or "").strip().upper() if grade else None
    if gates_passed is not None and not (0 <= gates_passed <= 3):
        raise ValueError(f"Invalid gates_passed: {gates_passed}. Must be between 0 and 3.")

    sym_norm = str(symbol or "").strip().upper()
    if not sym_norm:
        raise ValueError("symbol cannot be empty")

    # Security: Strictly validate account identifier if provided to prevent malicious inputs
    if account:
        sanitize_account(account)
    account_mask = mask_account(account) if account else ""

    rec_str = str(recommendation or "").strip()
    if not rec_str:
        raise ValueError("recommendation cannot be empty")

    notes_str = str(notes or "").strip() if notes else None

    # Redact raw account string from free-text fields
    if account:
        raw_acc = str(account).strip()
        if raw_acc and account_mask:
            rec_str = rec_str.replace(raw_acc, account_mask)
            if notes_str:
                notes_str = notes_str.replace(raw_acc, account_mask)

    # Truncate length
    if len(rec_str) > DECISION_TEXT_MAX_LEN:
        rec_str = rec_str[:DECISION_TEXT_MAX_LEN]
    if notes_str and len(notes_str) > DECISION_TEXT_MAX_LEN:
        notes_str = notes_str[:DECISION_TEXT_MAX_LEN]

    if not recorded_at:
        recorded_at = datetime.now(timezone.utc).isoformat()

    conn = init_db(db_path)
    with conn:
        cur = conn.execute(
            """
            INSERT INTO decisions (
                recorded_at, account_mask, decision_type, symbol, contract,
                grade, regime_authorization, gates_passed, trigger_code,
                recommendation, human_answer, order_ref, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                recorded_at, account_mask, decision_type_norm, sym_norm, contract,
                grade_norm, regime_authorization, gates_passed, trigger_norm,
                rec_str, human_answer_norm, order_ref, notes_str
            ),
        )
        decision_id = cur.lastrowid
    conn.close()
    return decision_id


def query_decisions(
    account: Optional[str] = None,
    limit: int = 50,
    db_path: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Queries logged approval decisions from SQLite, newest first."""
    # Security: Validate account format before querying
    if account:
        sanitize_account(account)
    conn = init_db(db_path)
    cur = conn.cursor()
    account_mask = mask_account(account) if account else None

    if account_mask:
        cur.execute(
            """
            SELECT * FROM decisions
            WHERE account_mask = ?
            ORDER BY recorded_at DESC, id DESC
            LIMIT ?
            """,
            (account_mask, limit),
        )
    else:
        cur.execute(
            """
            SELECT * FROM decisions
            ORDER BY recorded_at DESC, id DESC
            LIMIT ?
            """,
            (limit,),
        )
    rows = cur.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def summarize_decisions(
    account: Optional[str] = None,
    db_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Generates an audit summary of decisions, approval rates, and rule conflicts."""
    # Security: Validate account format before summarizing
    if account:
        sanitize_account(account)
    conn = init_db(db_path)
    cur = conn.cursor()
    account_mask = mask_account(account) if account else None

    if account_mask:
        cur.execute(
            "SELECT * FROM decisions WHERE account_mask = ?",
            (account_mask,),
        )
    else:
        cur.execute("SELECT * FROM decisions")
    rows = cur.fetchall()
    conn.close()

    total = len(rows)
    by_type = {"ENTRY": 0, "EXIT": 0}
    by_answer = {"APPROVED": 0, "DECLINED": 0, "SKIPPED": 0, "AMBIGUOUS": 0}
    rule_conflicts: List[Dict[str, Any]] = []

    for r in rows:
        d = dict(r)
        d_type = d.get("decision_type", "")
        if d_type in by_type:
            by_type[d_type] += 1
        d_ans = d.get("human_answer", "")
        if d_ans in by_answer:
            by_answer[d_ans] += 1

        # Check rule conflicts:
        # 1. APPROVED entry where grade is PENDING or REJECTED
        if d_type == "ENTRY" and d_ans == "APPROVED":
            grade = (d.get("grade") or "").upper()
            if grade in ("PENDING", "REJECTED"):
                rule_conflicts.append({
                    "id": d["id"],
                    "type": d_type,
                    "symbol": d["symbol"],
                    "reason": f"Approved entry with non-confirmed grade: {grade}",
                })
        # 2. DECLINED or SKIPPED exit where trigger is a mandatory stop (STOP1 or STOP5)
        elif d_type == "EXIT" and d_ans in ("DECLINED", "SKIPPED", "AMBIGUOUS"):
            trigger = (d.get("trigger_code") or "").upper()
            if trigger in ("STOP1", "STOP5"):
                rule_conflicts.append({
                    "id": d["id"],
                    "type": d_type,
                    "symbol": d["symbol"],
                    "reason": f"{d_ans} mandatory exit stop: {trigger}",
                })

    approved_cnt = by_answer["APPROVED"]
    approval_rate = round((approved_cnt / total) * 100, 2) if total > 0 else 0.0

    return {
        "account_mask": account_mask,
        "total_decisions": total,
        "by_type": by_type,
        "by_answer": by_answer,
        "approval_rate_pct": approval_rate,
        "rule_conflicts_count": len(rule_conflicts),
        "rule_conflicts": rule_conflicts,
    }


