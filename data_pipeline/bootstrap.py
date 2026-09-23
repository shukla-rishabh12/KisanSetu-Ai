# ============================================================
# KisanBazaar AI — Bootstrap Data Seeder
# ============================================================
# Ye ek standalone script hai jo pichhle N din ka data
# Government API se fetch karke SQLite me daalti hai.
#
# PURPOSE:
#   - Demo ke liye initial data seed karna
#   - Development me meaningful charts dekhne ke liye
#   - Testing ke liye real data
#
# PRODUCTION ME:
#   - Ye script nahi chalegi
#   - Daily scheduler sirf aaj ka data fetch karega
#   - Ye sirf ek-baar ka setup hai
#
# RUN:
#   python data_pipeline/bootstrap.py           (default 30 din)
#   python data_pipeline/bootstrap.py 90        (90 din)
#
# FEATURES:
#   - Checkpoint (resume capability)
#   - Progress logging
#   - Error handling (ek din fail ho to baaki continue)
#   - Final summary
# ============================================================

import sys
import json
import time
from datetime import date, timedelta
from pathlib import Path

# ------------------------------------------------------------
# PATH FIX
# ------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# Project imports
from data_pipeline.api_fetcher import fetch_data_for_date
from data_pipeline.cleaner import clean_records
from data_pipeline.validator import validate_records
from data_pipeline.database_loader import save_records
from database.db import init_db, count_rows
from core.logger import get_logger
from core.exceptions import DataFetchError

# Logger
logger = get_logger(__name__)


# ============================================================
# SECTION 1: CONFIG
# ============================================================

DEFAULT_DAYS = 30
CHECKPOINT_FILE = _PROJECT_ROOT / "data_pipeline" / ".bootstrap_checkpoint.json"

# API ko overload na karne ke liye har din ke fetch ke baad wait
SLEEP_BETWEEN_DAYS = 1.0  # seconds


# ============================================================
# SECTION 2: CHECKPOINT HELPERS
# ============================================================

def load_checkpoint() -> dict:
    """
    Checkpoint file load karta hai (agar exist kare).

    Returns:
        dict: {"last_completed_date": "YYYY-MM-DD", "days_total": int}
              ya {} agar koi checkpoint nahi hai.
    """
    if not CHECKPOINT_FILE.exists():
        return {}
    try:
        with open(CHECKPOINT_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"Checkpoint load fail: {e}")
        return {}


def save_checkpoint(last_date: date, days_total: int) -> None:
    """Checkpoint save karta hai."""
    try:
        CHECKPOINT_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(CHECKPOINT_FILE, "w", encoding="utf-8") as f:
            json.dump({
                "last_completed_date": last_date.strftime("%Y-%m-%d"),
                "days_total": days_total,
                "saved_at": date.today().strftime("%Y-%m-%d"),
            }, f, indent=2)
    except Exception as e:
        logger.warning(f"Checkpoint save fail: {e}")


def clear_checkpoint() -> None:
    """Checkpoint delete karta hai (successful completion ke baad)."""
    try:
        if CHECKPOINT_FILE.exists():
            CHECKPOINT_FILE.unlink()
    except Exception as e:
        logger.warning(f"Checkpoint delete fail: {e}")


# ============================================================
# SECTION 3: MAIN BOOTSTRAP FUNCTION
# ============================================================

def bootstrap(days: int = DEFAULT_DAYS, resume: bool = True) -> dict:
    """
    Pichhle `days` din ka data API se fetch karke SQLite me daalta hai.

    Args:
        days: Kitne din ka data (default 30).
        resume: Checkpoint se resume karna hai ya nahi (default True).

    Returns:
        dict: Summary {
            "days_attempted": int,
            "days_success": int,
            "days_failed": int,
            "total_records_inserted": int,
            "total_records_skipped": int,
            "start_date": str,
            "end_date": str,
        }
    """
    # --------------------------------------------------------
    # STEP 1: Setup — date range nikalo
    # --------------------------------------------------------
    end_date = date.today()
    start_date = end_date - timedelta(days=days - 1)

    logger.info("=" * 65)
    logger.info("KisanBazaar AI — Bootstrap Data Seeder")
    logger.info("=" * 65)
    logger.info(f"Days requested : {days}")
    logger.info(f"Date range     : {start_date} → {end_date}")

    # --------------------------------------------------------
    # STEP 2: Checkpoint check karo
    # --------------------------------------------------------
    checkpoint = load_checkpoint() if resume else {}
    resume_date = None

    if checkpoint and checkpoint.get("last_completed_date"):
        try:
            last_done = date.fromisoformat(checkpoint["last_completed_date"])
            resume_date = last_done + timedelta(days=1)

            # Agar resume date end_date se aage hai to kuch nahi karna
            if resume_date > end_date:
                logger.info("✅ Checkpoint ke hisaab se saara data already fetch ho chuka hai.")
                return {
                    "days_attempted": 0,
                    "days_success": 0,
                    "days_failed": 0,
                    "total_records_inserted": 0,
                    "total_records_skipped": 0,
                    "start_date": start_date.isoformat(),
                    "end_date": end_date.isoformat(),
                    "message": "Already complete (checkpoint)",
                }

            logger.info(f"📌 Resuming from checkpoint: {resume_date}")
        except Exception as e:
            logger.warning(f"Checkpoint invalid, starting fresh: {e}")
            resume_date = None

    current_date = resume_date if resume_date else start_date

    # --------------------------------------------------------
    # STEP 3: DB init
    # --------------------------------------------------------
    init_db()
    initial_count = count_rows("market_prices")
    logger.info(f"DB me existing records: {initial_count}")
    logger.info("=" * 65)

    # --------------------------------------------------------
    # STEP 4: Loop through each date
    # --------------------------------------------------------
    summary = {
        "days_attempted": 0,
        "days_success": 0,
        "days_failed": 0,
        "total_records_inserted": 0,
        "total_records_skipped": 0,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
    }

    current = current_date
    total_days = (end_date - current_date).days + 1
    day_index = 0

    while current <= end_date:
        day_index += 1
        summary["days_attempted"] += 1

        logger.info(f"\n📅 [{day_index}/{total_days}] Processing {current.isoformat()} ...")

        try:
            # --------------------------------------------------
            # 4.1: API Fetch
            # --------------------------------------------------
            raw_records = fetch_data_for_date(current)
            logger.info(f"   Fetched: {len(raw_records)} raw records")

            if not raw_records:
                logger.info(f"   ⚠️  Koi record nahi mila is date pe, skip.")
                summary["days_success"] += 1  # Empty day bhi success maana
                save_checkpoint(current, days)
                current += timedelta(days=1)
                time.sleep(SLEEP_BETWEEN_DAYS)
                continue

            # --------------------------------------------------
            # 4.2: Clean
            # --------------------------------------------------
            cleaned, clean_skipped = clean_records(raw_records)
            logger.info(f"   Cleaned: {len(cleaned)} (skipped {clean_skipped})")

            # --------------------------------------------------
            # 4.3: Validate
            # --------------------------------------------------
            valid, invalid = validate_records(cleaned)
            logger.info(f"   Validated: {len(valid)} (invalid {len(invalid)})")

            # --------------------------------------------------
            # 4.4: Save to SQLite
            # --------------------------------------------------
            result = save_records(
                records=valid,
                sync_date=current.isoformat(),
                records_fetched=len(raw_records),
                duplicates_prechecked=0,
                invalid_count=len(invalid) + clean_skipped,
            )

            logger.info(
                f"   💾 Inserted: {result['inserted']}, "
                f"Skipped: {result['skipped']}"
            )

            summary["days_success"] += 1
            summary["total_records_inserted"] += result["inserted"]
            summary["total_records_skipped"] += result["skipped"]

            # --------------------------------------------------
            # 4.5: Checkpoint save
            # --------------------------------------------------
            save_checkpoint(current, days)

        except DataFetchError as e:
            # API error — is din ko skip karo, agle din continue
            logger.error(f"   ❌ Data fetch fail ({current}): {e}")
            summary["days_failed"] += 1

        except Exception as e:
            logger.exception(f"   ❌ Unexpected error ({current}): {e}")
            summary["days_failed"] += 1

        # Next date
        current += timedelta(days=1)

        # API ko rest do
        if current <= end_date:
            time.sleep(SLEEP_BETWEEN_DAYS)

    # --------------------------------------------------------
    # STEP 5: Final summary
    # --------------------------------------------------------
    final_count = count_rows("market_prices")

    logger.info("\n" + "=" * 65)
    logger.info("✅ Bootstrap COMPLETE")
    logger.info("=" * 65)
    logger.info(f"Days attempted      : {summary['days_attempted']}")
    logger.info(f"Days success        : {summary['days_success']}")
    logger.info(f"Days failed         : {summary['days_failed']}")
    logger.info(f"Records inserted    : {summary['total_records_inserted']}")
    logger.info(f"Records skipped     : {summary['total_records_skipped']}")
    logger.info(f"DB total before     : {initial_count}")
    logger.info(f"DB total after      : {final_count}")
    logger.info("=" * 65)

    # Checkpoint clear karo (complete ho gaya)
    if summary["days_failed"] == 0:
        clear_checkpoint()
        logger.info("Checkpoint cleared.")

    return summary


# ============================================================
# SECTION 4: DIRECT RUN
# ============================================================

if __name__ == "__main__":
    # Command line se days lo (default 30)
    if len(sys.argv) > 1:
        try:
            days_arg = int(sys.argv[1])
            if days_arg < 1 or days_arg > 365:
                print("⚠️  Days 1-365 ke beech hona chahiye. Default 30 use kar rahe hain.")
                days_arg = DEFAULT_DAYS
        except ValueError:
            print("⚠️  Invalid days argument. Default 30 use kar rahe hain.")
            days_arg = DEFAULT_DAYS
    else:
        days_arg = DEFAULT_DAYS

    print()
    print("=" * 65)
    print(f"🌾 KisanBazaar AI — Bootstrap ({days_arg} din ka data)")
    print("=" * 65)
    print()
    print("NOTE: Ye script pichhle N din ka data Government API se fetch karegi.")
    print(f"      API calls: ~{days_arg} din × multiple pages = {days_arg * 3}+ requests")
    print(f"      Estimated time: {days_arg * 5 // 60} - {days_arg * 10 // 60} minutes")
    print()

    try:
        result = bootstrap(days=days_arg)
        print()
        print("=" * 65)
        print("🎉 Bootstrap done!")
        print("=" * 65)
        print(f"Start date          : {result['start_date']}")
        print(f"End date            : {result['end_date']}")
        print(f"Days attempted      : {result['days_attempted']}")
        print(f"Days success        : {result['days_success']}")
        print(f"Days failed         : {result['days_failed']}")
        print(f"Records inserted    : {result['total_records_inserted']}")
        print(f"Records skipped     : {result['total_records_skipped']}")
        print("=" * 65)
        print()
        print("Ab browser me dashboard refresh karo:")
        print("  http://127.0.0.1:5000/dashboard")
        print()

    except KeyboardInterrupt:
        print("\n\n⚠️  User ne interrupt kiya. Checkpoint saved hai.")
        print("   Dobara run karoge to resume hoga.\n")
    except Exception as e:
        print(f"\n❌ Bootstrap failed: {e}\n")
        logger.exception("Bootstrap failed")