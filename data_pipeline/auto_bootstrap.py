# ============================================================
# KisanBazaar AI — Auto Bootstrap
# ============================================================
# Ye script server start hone pe check karta hai ki DB me
# enough fresh data hai ya nahi. Agar nahi, to background
# thread me bootstrap chala deta hai (non-blocking).
#
# WHY NEEDED:
#   - Render free tier pe SQLite ephemeral hai (restart pe gayab)
#   - Har restart pe 90 din ka data fetch karna padega
#   - Ye script automatic karta hai — manual run nahi karna
#
# FLOW:
#   1. App start
#   2. Ye check karta hai: "DB me data hai? Fresh hai?"
#   3. Agar nahi → background thread me bootstrap start
#   4. Flask turant serve karna shuru karta hai (block nahi hota)
#   5. Data background me bharti jaati hai
#
# MEMORY SAFE:
#   - Bootstrap ek din ka data fetch karta hai (~20K records)
#   - SQLite me save karta hai
#   - Phir agla din
#   - Peak memory: ~100-150 MB (512 MB me aaram se)
# ============================================================

import sys
import threading
from datetime import date, datetime
from pathlib import Path

# ------------------------------------------------------------
# PATH FIX
# ------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# Project imports
from core.logger import get_logger

logger = get_logger(__name__)


# ============================================================
# GLOBAL STATE
# ============================================================
# Ek waqt me ek hi bootstrap chalega (thread safe).

_bootstrap_thread = None
_bootstrap_lock = threading.Lock()


# ============================================================
# SECTION 1: DB STATE CHECK
# ============================================================

def _check_db_state() -> dict:
    """
    Check karta hai ki DB me kya data hai.
    
    Returns:
        dict: {
            "record_count": int,
            "max_date": str or None,
            "days_old": int or None,
            "is_empty": bool,
            "is_stale": bool,
        }
    """
    from database.db import fetch_one
    
    result = {
        "record_count": 0,
        "max_date": None,
        "days_old": None,
        "is_empty": True,
        "is_stale": True,
    }
    
    try:
        row = fetch_one(
            "SELECT COUNT(*) as cnt, MAX(arrival_date) as max_date "
            "FROM market_prices"
        )
        
        if not row:
            return result
        
        result["record_count"] = row["cnt"] or 0
        result["max_date"] = row["max_date"]
        result["is_empty"] = (result["record_count"] == 0)
        
        if result["max_date"]:
            try:
                max_dt = date.fromisoformat(result["max_date"])
                days_old = (date.today() - max_dt).days
                result["days_old"] = days_old
                # Data > 3 din purana = stale
                result["is_stale"] = days_old > 3
            except Exception as e:
                logger.warning(f"Date parse fail: {result['max_date']} — {e}")
                result["is_stale"] = True
        
        return result
    
    except Exception as e:
        logger.warning(f"DB state check fail: {e}")
        return result


# ============================================================
# SECTION 2: BOOTSTRAP THREAD WORKER
# ============================================================

def _bootstrap_worker(days: int, reason: str):
    """
    Background thread me bootstrap run karta hai.
    Exceptions catch karke log karta hai (crash nahi karta).
    """
    try:
        logger.info("=" * 60)
        logger.info(f"🔧 AUTO-BOOTSTRAP starting ({days} days)")
        logger.info(f"   Reason: {reason}")
        logger.info("=" * 60)
        
        # Import inside thread (heavy imports avoided at module load)
        from data_pipeline.bootstrap import bootstrap
        
        result = bootstrap(days=days, resume=True)
        
        logger.info("=" * 60)
        logger.info("✅ AUTO-BOOTSTRAP complete")
        logger.info(f"   Days success: {result.get('days_success', '?')}")
        logger.info(f"   Days failed : {result.get('days_failed', '?')}")
        logger.info(f"   Records in  : {result.get('total_records_inserted', '?')}")
        logger.info("=" * 60)
    
    except Exception as e:
        logger.exception(f"❌ AUTO-BOOTSTRAP failed: {e}")
    
    finally:
        # Thread reference clear karo
        global _bootstrap_thread
        with _bootstrap_lock:
            _bootstrap_thread = None


# ============================================================
# SECTION 3: PUBLIC API
# ============================================================

def start_auto_bootstrap_if_needed(
    days: int = 90,
    min_records: int = 5000,
    max_staleness_days: int = 3,
) -> dict:
    """
    Check karta hai aur zaroorat ho to background bootstrap start karta hai.
    Non-blocking — turant return karta hai.
    
    Args:
        days: Kitne din ka data fetch karna hai (default 90).
        min_records: Minimum records DB me hone chahiye (default 5000).
        max_staleness_days: Data kitne din purana ho to stale (default 3).
    
    Returns:
        dict: {
            "action": "skipped" | "started" | "already_running",
            "reason": str,
        }
    """
    global _bootstrap_thread
    
    # Agar pehle se chal raha hai to dobara mat start karo
    with _bootstrap_lock:
        if _bootstrap_thread is not None and _bootstrap_thread.is_alive():
            logger.info("⏸  Auto-bootstrap already running — skipping")
            return {
                "action": "already_running",
                "reason": "bootstrap already in progress",
            }
    
    # DB state check
    state = _check_db_state()
    
    logger.info(
        f"DB state: records={state['record_count']}, "
        f"max_date={state['max_date']}, days_old={state['days_old']}"
    )
    
    # Decide: skip ya start?
    reasons = []
    
    if state["is_empty"]:
        reasons.append("DB empty")
    elif state["record_count"] < min_records:
        reasons.append(f"only {state['record_count']} records")
    
    if state["days_old"] is not None and state["days_old"] > max_staleness_days:
        reasons.append(f"data {state['days_old']} days old")
    
    if not reasons:
        logger.info("✅ DB has fresh data — auto-bootstrap not needed")
        return {
            "action": "skipped",
            "reason": f"data OK ({state['record_count']} records)",
        }
    
    # Start bootstrap in background
    reason_str = ", ".join(reasons)
    
    with _bootstrap_lock:
        _bootstrap_thread = threading.Thread(
            target=_bootstrap_worker,
            args=(days, reason_str),
            daemon=True,     # Flask exit hone pe thread bhi khatam
            name="auto-bootstrap",
        )
        _bootstrap_thread.start()
    
    logger.warning(f"⚠️  Auto-bootstrap STARTED in background: {reason_str}")
    
    return {
        "action": "started",
        "reason": reason_str,
    }


def get_bootstrap_status() -> dict:
    """
    Bootstrap ka current status return karta hai.
    
    Returns:
        dict: {"running": bool, "db_state": {...}}
    """
    with _bootstrap_lock:
        running = _bootstrap_thread is not None and _bootstrap_thread.is_alive()
    
    return {
        "running": running,
        "db_state": _check_db_state(),
    }


# ============================================================
# SECTION 4: DIRECT RUN (test only)
# ============================================================
if __name__ == "__main__":
    print("=" * 65)
    print("KisanBazaar AI — Auto Bootstrap Test")
    print("=" * 65)
    
    print("\n--- DB State Check ---")
    state = _check_db_state()
    for k, v in state.items():
        print(f"  {k}: {v}")
    
    print("\n--- Starting auto-bootstrap (if needed) ---")
    result = start_auto_bootstrap_if_needed(days=90)
    print(f"  Action: {result['action']}")
    print(f"  Reason: {result['reason']}")
    
    if result["action"] == "started":
        print("\n⚠️  Bootstrap background me chal raha hai.")
        print("   Flask app turant start ho jayega. Data background me bharega.")
    else:
        print("\n✅ DB already fresh — koi action nahi.")