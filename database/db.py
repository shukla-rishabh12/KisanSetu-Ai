# ============================================================
# KisanBazaar AI — Database Layer (SQLite)
# ============================================================
# Ye file SQLite database ka CENTRAL connection layer hai.
# Poora project isi file ke through DB se baat karega.
#
# Features:
#   1. Safe SQLite connection (thread-safe, WAL mode)
#   2. schema.sql execute karke tables create
#   3. Query helpers (fetch_one, fetch_all, execute, insert_many)
#   4. Context manager for automatic commit/rollback/close
#   5. Row factory → result dictionary ki tarah milta hai
#
# DESIGN PRINCIPLE:
#   - Har module isi file ko import karke DB use karega.
#   - Koi bhi module direct sqlite3.connect() nahi karega.
#   - Isse connection handling ek jagah centralized rahegi.
# ============================================================

import sqlite3
import logging
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable, Optional

# Config se paths import karo
from config import DatabaseConfig

# Logger setup (debugging ke liye)
logger = logging.getLogger(__name__)


# ============================================================
# SECTION 1: CONNECTION MANAGEMENT
# ============================================================

def get_connection() -> sqlite3.Connection:
    """
    SQLite database ka new connection return karta hai.

    Configuration:
      - Row factory set hai → row['column_name'] se access ho sakta hai.
      - WAL mode ON → multiple readers + 1 writer ek saath kaam kar sakte hain.
      - Foreign keys ON → integrity enforcement.
      - Timeout 30s → agar DB locked hai to wait karega.

    Returns:
        sqlite3.Connection: Ready-to-use connection object.
    """
    # Ensure karo ki DB folder exist karta hai
    DatabaseConfig.DB_FOLDER.mkdir(parents=True, exist_ok=True)

    # Connection banao
    conn = sqlite3.connect(
        str(DatabaseConfig.DB_PATH),
        timeout=30.0,
        check_same_thread=False,   # Flask + scheduler dono use karenge
    )

    # Row factory: rows ko dictionary ki tarah access karne ke liye
    # Example: row["market"], row["modal_price"]
    conn.row_factory = sqlite3.Row

    # WAL mode: better concurrency (ek writer, multiple readers)
    conn.execute("PRAGMA journal_mode = WAL;")

    # Foreign keys enable karo (agar future me relations add karein)
    conn.execute("PRAGMA foreign_keys = ON;")

    # Synchronous NORMAL → speed aur safety ka balance
    conn.execute("PRAGMA synchronous = NORMAL;")

    return conn


@contextmanager
def db_session():
    """
    Context manager for safe DB session.

    Usage:
        with db_session() as conn:
            cursor = conn.execute("SELECT ...")
            ...

    Ye automatically:
      - Success pe commit karega
      - Exception pe rollback karega
      - Finally connection close karega

    Isse manual commit/rollback/close ka jhanjhat khatam.
    """
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception as e:
        conn.rollback()
        logger.error(f"DB session error, rolling back: {e}")
        raise
    finally:
        conn.close()


# ============================================================
# SECTION 2: SCHEMA INITIALIZATION
# ============================================================

def init_db() -> None:
    """
    schema.sql file read karke execute karta hai.
    Saari tables aur indexes create ho jaate hain (IF NOT EXISTS use hua hai).

    Idempotent hai — bar-bar chalao, safe hai.
    App start hone pe ek baar call hota hai.
    """
    schema_path = DatabaseConfig.SCHEMA_PATH

    if not schema_path.exists():
        raise FileNotFoundError(
            f"Schema file nahi mili: {schema_path}. "
            "database/schema.sql verify karo."
        )

    # Schema file read karo
    with open(schema_path, "r", encoding="utf-8") as f:
        schema_sql = f.read()

    # Execute karo
    with db_session() as conn:
        conn.executescript(schema_sql)

    logger.info("✅ Database schema initialized (tables + indexes ready).")


# ============================================================
# SECTION 3: QUERY HELPERS
# ============================================================
# Ye helpers har module use karega. Inhe use karke SQL queries
# safely run kar sakte ho without manual connection handling.
# ============================================================

def fetch_all(query: str, params: Iterable = ()) -> list[dict]:
    """
    SELECT query chalao aur SAARE rows return karo.

    Args:
        query: SQL SELECT statement (placeholders '?' use karo).
        params: Query parameters tuple/list.

    Returns:
        list[dict]: Har row dictionary form me.

    Example:
        rows = fetch_all(
            "SELECT * FROM market_prices WHERE market = ?",
            ("Kanpur",)
        )
    """
    with db_session() as conn:
        cursor = conn.execute(query, tuple(params))
        rows = cursor.fetchall()
        # sqlite3.Row ko dict me convert karo (JSON serializable)
        return [dict(row) for row in rows]


def fetch_one(query: str, params: Iterable = ()) -> Optional[dict]:
    """
    SELECT query chalao aur SIRF EK row return karo.
    Agar kuch nahi mila to None.

    Example:
        row = fetch_one(
            "SELECT * FROM market_prices WHERE id = ?",
            (5,)
        )
    """
    with db_session() as conn:
        cursor = conn.execute(query, tuple(params))
        row = cursor.fetchone()
        return dict(row) if row else None


def execute_query(query: str, params: Iterable = ()) -> int:
    """
    INSERT / UPDATE / DELETE query chalao.

    Returns:
        int: Last inserted row id (INSERT) ya affected row count (UPDATE/DELETE).

    Example:
        new_id = execute_query(
            "INSERT INTO market_prices (...) VALUES (?, ?, ...)",
            (val1, val2, ...)
        )
    """
    with db_session() as conn:
        cursor = conn.execute(query, tuple(params))
        # Agar INSERT hua to lastrowid, warna rowcount
        return cursor.lastrowid if cursor.lastrowid else cursor.rowcount


def insert_one(table: str, data: dict) -> int:
    """
    Ek row insert karo dictionary se.
    Automatically column names aur placeholders banata hai.

    Args:
        table: Table name (e.g., "market_prices").
        data: Dict {column_name: value}.

    Returns:
        int: Naya row id.

    Example:
        insert_one("market_prices", {
            "state": "Uttar Pradesh",
            "market": "Kanpur",
            "commodity": "Potato",
            "arrival_date": "2026-09-15",
            "modal_price": 2750.0
        })
    """
    if not data:
        raise ValueError("insert_one: data dict khali hai.")

    columns = ", ".join(data.keys())
    placeholders = ", ".join(["?"] * len(data))
    values = tuple(data.values())

    query = f"INSERT INTO {table} ({columns}) VALUES ({placeholders})"

    with db_session() as conn:
        cursor = conn.execute(query, values)
        return cursor.lastrowid


def insert_many(table: str, rows: list[dict], or_ignore: bool = True) -> int:
    """
    Bulk insert karo — ek hi transaction me multiple rows.
    Daily API fetch me 10,000+ rows insert karne ke liye useful.

    Args:
        table: Table name.
        rows: List of dicts (same keys hone chahiye).
        or_ignore: True → duplicate rows silently skip (INSERT OR IGNORE).

    Returns:
        int: Kitni rows actually insert hui.
    """
    if not rows:
        return 0

    # Sabhi rows ke same columns hone chahiye
    columns = list(rows[0].keys())
    placeholders = ", ".join(["?"] * len(columns))
    col_names = ", ".join(columns)

    insert_keyword = "INSERT OR IGNORE" if or_ignore else "INSERT"
    query = f"{insert_keyword} INTO {table} ({col_names}) VALUES ({placeholders})"

    # Rows ko tuples me convert karo
    values = [tuple(row.get(col) for col in columns) for row in rows]

    with db_session() as conn:
        cursor = conn.executemany(query, values)
        inserted = cursor.rowcount
        logger.info(f"Bulk insert into {table}: {inserted}/{len(rows)} rows.")
        return inserted


def table_exists(table_name: str) -> bool:
    """
    Check karo ki table exist karti hai ya nahi.
    """
    row = fetch_one(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,)
    )
    return row is not None


def count_rows(table: str, where: str = "", params: Iterable = ()) -> int:
    """
    Table me kitni rows hain count karo (optional WHERE clause ke saath).

    Example:
        count_rows("market_prices", "market = ?", ("Kanpur",))
    """
    query = f"SELECT COUNT(*) as cnt FROM {table}"
    if where:
        query += f" WHERE {where}"

    row = fetch_one(query, params)
    return row["cnt"] if row else 0


# ============================================================
# SECTION 4: DIRECT RUN — Quick Test
# ============================================================
if __name__ == "__main__":
    # Logger basic config (test ke liye)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s"
    )

    print("=" * 55)
    print("KisanBazaar AI — Database Layer Test")
    print("=" * 55)

    # 1. DB init karo (tables create honge)
    init_db()

    # 2. Tables verify karo
    tables = ["market_prices", "data_sync_logs", "model_versions", "prediction_logs"]
    for t in tables:
        exists = table_exists(t)
        count = count_rows(t) if exists else 0
        print(f"  {t:20s} → {'✅ exists' if exists else '❌ missing'}  (rows: {count})")

    print("=" * 55)
    print(f"DB file: {DatabaseConfig.DB_PATH}")
    print("✅ Database layer ready.")