# ============================================================
# KisanBazaar AI — Database Loader
# ============================================================
# Ye file VALIDATED records ko SQLite me insert karti hai.
# Poora data pipeline is file pe khatam hota hai.
#
# KYA KARTA HAI:
#   1. Valid records ko bulk insert (INSERT OR IGNORE)
#   2. Duplicate rows silently skip
#   3. Sync log entry banata hai (data_sync_logs table)
#   4. Retention cleanup (2 saal se purane records delete)
#   5. Insert count, duplicate count, error count track
#
# FLOW:
#   API → Clean → Validate → [YE FILE] → SQLite
# ============================================================

import sys
from datetime import date, datetime, timedelta
from pathlib import Path

# ------------------------------------------------------------
# PATH FIX
# ------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# Project imports
from config import DatabaseConfig
from database.db import (
    db_session,
    insert_many,
    count_rows,
    fetch_one,
    execute_query,
    init_db,
)
from core.logger import get_logger

# Logger
logger = get_logger(__name__)


# ============================================================
# SECTION 1: SANITIZE FOR INSERT
# ============================================================
# SQLite me NULL values UNIQUE constraint me hamesha DIFFERENT
# maani jaati hain (NULL != NULL). Isse duplicate detection fail
# ho jaati hai. Isliye insert se pehle unique columns me None → ""
# kar dete hain.
# ============================================================

# Ye columns UNIQUE constraint ka part hain (schema.sql dekh lo).
UNIQUE_COLUMNS = (
    "state",
    "district",
    "market",
    "commodity",
    "variety",
    "grade",
    "arrival_date",
)


def _sanitize_record(record: dict) -> dict:
    """
    Insert se pehle record ko sanitize karta hai.

    - UNIQUE constraint wale columns me None → ""
      (SQLite NULL handling ki wajah se ye zaroori hai)
    - Baaki columns waise hi rahenge (None allowed)

    Example:
        {"market": "Kanpur", "variety": None, "modal_price": 2750.0}
        → {"market": "Kanpur", "variety": "", "modal_price": 2750.0}
    """
    sanitized = dict(record)  # copy banao (original ko modify na karein)
    for col in UNIQUE_COLUMNS:
        if col in sanitized and sanitized[col] is None:
            sanitized[col] = ""
    return sanitized


# ============================================================
# SECTION 2: SYNC LOG HELPERS
# ============================================================

def _start_sync_log(sync_date: str) -> int:
    """
    Naya sync log entry banata hai (status='RUNNING').
    Returns log id.

    Ye entry daily fetch ke shuru hone pe banti hai. Agar beech me
    process fail ho jaye, to pata chalega ki kuch issue tha.
    """
    with db_session() as conn:
        cursor = conn.execute(
            """
            INSERT INTO data_sync_logs
                (sync_date, started_at, status)
            VALUES (?, ?, ?)
            """,
            (sync_date, datetime.now().isoformat(timespec="seconds"), "RUNNING"),
        )
        log_id = cursor.lastrowid
        logger.debug(f"Sync log started: id={log_id}, date={sync_date}")
        return log_id


def _finish_sync_log(
    log_id: int,
    status: str,
    records_fetched: int = 0,
    records_inserted: int = 0,
    records_updated: int = 0,
    duplicates: int = 0,
    errors: int = 0,
    error_message: str = None,
) -> None:
    """
    Sync log entry ko update karta hai (completed_at + counts + status).
    """
    with db_session() as conn:
        conn.execute(
            """
            UPDATE data_sync_logs
            SET completed_at     = ?,
                status           = ?,
                records_fetched  = ?,
                records_inserted = ?,
                records_updated  = ?,
                duplicates       = ?,
                errors           = ?,
                error_message    = ?
            WHERE id = ?
            """,
            (
                datetime.now().isoformat(timespec="seconds"),
                status,
                records_fetched,
                records_inserted,
                records_updated,
                duplicates,
                errors,
                error_message,
                log_id,
            ),
        )
        logger.debug(f"Sync log finished: id={log_id}, status={status}")


# ============================================================
# SECTION 3: RETENTION CLEANUP
# ============================================================

def cleanup_old_records() -> int:
    """
    2 saal se purane records delete karta hai (rolling retention).

    SRS ke hisaab se: SQLite me sirf latest 2 years ka data rakhna hai.
    Ye function daily insert ke baad chalta hai.

    Returns:
        int: Kitne records delete hue.
    """
    # Cutoff date: aaj se 2 saal pehle
    cutoff_date = (
        date.today() - timedelta(days=365 * DatabaseConfig.RETENTION_YEARS)
    ).strftime("%Y-%m-%d")

    logger.info(f"Retention cleanup: deleting records older than {cutoff_date}")

    with db_session() as conn:
        cursor = conn.execute(
            "DELETE FROM market_prices WHERE arrival_date < ?",
            (cutoff_date,),
        )
        deleted = cursor.rowcount

    if deleted > 0:
        logger.info(f"✅ Retention cleanup: {deleted} purane records delete hue")
    else:
        logger.debug("Retention cleanup: koi purana record nahi mila")

    return deleted


# ============================================================
# SECTION 4: MAIN INSERT FUNCTION
# ============================================================

def save_records(
    records: list[dict],
    sync_date: str,
    records_fetched: int = None,
    duplicates_prechecked: int = 0,
    invalid_count: int = 0,
) -> dict:
    """
    Validated records ko SQLite me insert karta hai.

    Args:
        records: Validated + cleaned records (list of dict).
        sync_date: Kis date ka data hai (YYYY-MM-DD).
        records_fetched: API se total kitne records aaye the (logging ke liye).
        duplicates_prechecked: Validator ne kitne within-batch duplicates hataye.
        invalid_count: Validator ne kitne invalid records reject kiye.

    Returns:
        dict: {
            "inserted": int,      # Naye rows insert hue
            "skipped": int,       # Duplicate ki wajah se skip hue
            "errors": int,        # Insert fail hue
            "deleted_old": int,   # Retention cleanup me delete hue
            "total_valid": int,   # Input me kitne records the
        }

    Example:
        result = save_records(
            records=valid_records,
            sync_date="2026-09-15",
            records_fetched=18500,
            duplicates_prechecked=10,
            invalid_count=5,
        )
        print(f"Inserted: {result['inserted']}")
    """
    # Ensure tables exist (idempotent — safe hai)
    init_db()

    # Sync log shuru karo
    log_id = _start_sync_log(sync_date)

    # Result dict default values ke saath
    result = {
        "inserted": 0,
        "skipped": 0,
        "errors": 0,
        "deleted_old": 0,
        "total_valid": len(records) if records else 0,
    }

    try:
        # --------------------------------------------------------
        # STEP 1: Empty records case
        # --------------------------------------------------------
        if not records:
            logger.info(f"Koi valid record nahi hai date {sync_date} ke liye.")
            _finish_sync_log(
                log_id,
                status="SUCCESS",
                records_fetched=records_fetched or 0,
                duplicates=duplicates_prechecked,
                errors=invalid_count,
            )
            return result

        # --------------------------------------------------------
        # STEP 2: Bulk insert (INSERT OR IGNORE)
        # --------------------------------------------------------
        # Unique constraint ki wajah se duplicates skip ho jayenge.
        # Ye idempotent hai — same data dobara aaye to kuch nahi hoga.
        logger.info(f"Inserting {len(records)} records into market_prices...")

        # Sanitize: None → "" for unique columns (SQLite NULL handling)
        sanitized_records = [_sanitize_record(r) for r in records]

        inserted = insert_many("market_prices", sanitized_records, or_ignore=True)
        result["inserted"] = inserted

        # Skipped = total_valid - inserted
        # (kyunki INSERT OR IGNORE ne baaki skip kar diye = duplicates)
        skipped = len(records) - inserted
        result["skipped"] = skipped

        logger.info(
            f"✅ Insert complete: {inserted} naye records, "
            f"{skipped} duplicates skip hue."
        )

        # --------------------------------------------------------
        # STEP 3: Retention cleanup (2 saal se purane delete)
        # --------------------------------------------------------
        deleted_old = cleanup_old_records()
        result["deleted_old"] = deleted_old

        # --------------------------------------------------------
        # STEP 4: Sync log update (SUCCESS)
        # --------------------------------------------------------
        _finish_sync_log(
            log_id,
            status="SUCCESS",
            records_fetched=records_fetched or len(records),
            records_inserted=inserted,
            duplicates=duplicates_prechecked + skipped,
            errors=invalid_count,
        )

    except Exception as e:
        # --------------------------------------------------------
        # ERROR CASE: Sync log me fail mark karo
        # --------------------------------------------------------
        logger.exception(f"Insert fail hua: {e}")
        result["errors"] = len(records) if records else 0

        try:
            _finish_sync_log(
                log_id,
                status="FAILED",
                records_fetched=records_fetched or 0,
                errors=len(records) if records else 0,
                error_message=str(e)[:500],  # first 500 chars
            )
        except Exception as log_err:
            logger.error(f"Sync log update bhi fail: {log_err}")

        # Exception aage bhejo — caller decide karega kya karna hai
        raise

    return result


# ============================================================
# SECTION 5: PIPELINE ORCHESTRATOR (Optional Convenience)
# ============================================================

def load_from_api(
    target_date: date,
    clean_batch_size_log: bool = True,
) -> dict:
    """
    End-to-end convenience function: API se fetch → clean → validate → insert.

    Ye function real project me daily scheduler use karega.
    Debugging ke liye bhi useful — ek line me pura pipeline chalao.

    Args:
        target_date: Kis date ka data fetch karna hai.

    Returns:
        dict: Result summary (same as save_records).
    """
    # Lazy imports taaki circular dependency na ho
    from data_pipeline.api_fetcher import fetch_data_for_date
    from data_pipeline.cleaner import clean_records
    from data_pipeline.validator import validate_records

    sync_date_str = target_date.strftime("%Y-%m-%d")
    logger.info("=" * 55)
    logger.info(f"Pipeline START: {sync_date_str}")
    logger.info("=" * 55)

    # 1. Fetch
    raw_records = fetch_data_for_date(target_date)
    logger.info(f"[1/3] Fetched: {len(raw_records)} raw records")

    # 2. Clean
    cleaned, clean_skipped = clean_records(raw_records)
    logger.info(f"[2/3] Cleaned: {len(cleaned)} (skipped {clean_skipped})")

    # 3. Validate
    valid, invalid = validate_records(cleaned)
    logger.info(f"[3/3] Validated: {len(valid)} (invalid {len(invalid)})")

    # 4. Save
    result = save_records(
        records=valid,
        sync_date=sync_date_str,
        records_fetched=len(raw_records),
        duplicates_prechecked=0,   # validator ne handle kar liya
        invalid_count=len(invalid) + clean_skipped,
    )

    logger.info("=" * 55)
    logger.info(f"Pipeline DONE: {result}")
    logger.info("=" * 55)

    return result


# ============================================================
# SECTION 6: DIRECT RUN — Quick Test
# ============================================================
if __name__ == "__main__":
    print("=" * 60)
    print("KisanBazaar AI — Database Loader Test")
    print("=" * 60)

    # Step 1: DB init
    init_db()

    # Step 2: Sample records (test ke liye)
    # IMPORTANT: unique columns me None ki jagah "" use kar rahe hain
    # (SQLite NULL handling ki wajah se)
    today_str = date.today().strftime("%Y-%m-%d")
    sample_records = [
        {
            "state": "Uttar Pradesh",
            "district": "Kanpur Nagar",
            "market": "Kanpur",
            "commodity": "Potato",
            "variety": "Jyoti",
            "grade": "",
            "arrival_date": today_str,
            "min_price": 2500.0,
            "max_price": 3000.0,
            "modal_price": 2750.0,
            "source": "test_loader",
        },
        {
            "state": "Uttar Pradesh",
            "district": "Kanpur Nagar",
            "market": "Kanpur",
            "commodity": "Tomato",
            "variety": "Local",
            "grade": "",
            "arrival_date": today_str,
            "min_price": 1500.0,
            "max_price": 2000.0,
            "modal_price": 1750.0,
            "source": "test_loader",
        },
    ]

    print(f"\n--- Test 1: Insert {len(sample_records)} new records ---")
    result1 = save_records(
        records=sample_records,
        sync_date=today_str,
        records_fetched=len(sample_records),
    )
    print(f"Result: {result1}")

    print(f"\n--- Test 2: Insert SAME records again (should skip as duplicates) ---")
    result2 = save_records(
        records=sample_records,
        sync_date=today_str,
        records_fetched=len(sample_records),
    )
    print(f"Result: {result2}")
    print("(Expected: inserted=0, skipped=2)")

    # Count check
    total = count_rows("market_prices")
    print(f"\n--- market_prices total rows: {total} ---")
    print("(Expected: 2)")

    # Latest sync log
    latest_log = fetch_one(
        "SELECT * FROM data_sync_logs ORDER BY id DESC LIMIT 1"
    )
    print(f"\n--- Latest sync log ---")
    if latest_log:
        for k, v in latest_log.items():
            print(f"  {k}: {v}")

    print("\n" + "=" * 60)
    print("✅ Database loader test complete.")