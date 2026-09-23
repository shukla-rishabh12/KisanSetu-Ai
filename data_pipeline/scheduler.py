# ============================================================
# KisanBazaar AI — Daily Data Fetch Scheduler
# ============================================================
# Ye file APScheduler use karke daily API fetch schedule karti hai.
#
# KAAM:
#   - Roz raat 11:30 PM (configurable) pe API se data fetch
#   - Clean → Validate → SQLite
#   - Sync log maintain
#   - Flask ke saath ek hi process me chalti hai (background thread)
#
# USAGE (app.py me):
#   from data_pipeline.scheduler import start_scheduler
#   start_scheduler()
#
# MANUAL TEST:
#   python data_pipeline/scheduler.py
# ============================================================

import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

# ------------------------------------------------------------
# PATH FIX
# ------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# Third-party
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

# Project imports
from config import GovernmentAPIConfig
from core.logger import get_logger

# Logger
logger = get_logger(__name__)


# ============================================================
# GLOBAL SCHEDULER INSTANCE
# ============================================================
# Ek hi scheduler instance rakhte hain (singleton pattern).
# Multiple baar start_scheduler() call karne pe duplicate jobs nahi banenge.
# ============================================================

_scheduler = None


# ============================================================
# SECTION 1: DAILY FETCH JOB
# ============================================================

def _daily_fetch_job():
    """
    Ye function roz scheduler se trigger hoti hai.

    Steps:
      1. Aaj ka data fetch (agar nahi mila to kal ka try)
      2. Clean → Validate → Save
      3. Logs
    """
    logger.info("=" * 60)
    logger.info(f"🕐 Daily fetch job starting at {datetime.now().isoformat()}")
    logger.info("=" * 60)

    try:
        # Lazy imports taaki circular dependency na ho
        from data_pipeline.api_fetcher import fetch_data_for_date
        from data_pipeline.cleaner import clean_records
        from data_pipeline.validator import validate_records
        from data_pipeline.database_loader import save_records

        # Government API usually 1-2 din purana data deta hai.
        # Aaj se 2 din pehle tak try karo.
        target_date = None
        raw_records = []

        for days_back in range(0, 4):
            candidate = date.today() - timedelta(days=days_back)
            logger.info(f"Trying to fetch data for {candidate.isoformat()}...")
            try:
                raw_records = fetch_data_for_date(candidate)
                if raw_records:
                    target_date = candidate
                    logger.info(f"✅ Data mila for {target_date.isoformat()} ({len(raw_records)} records)")
                    break
            except Exception as fetch_err:
                logger.warning(f"Fetch fail for {candidate.isoformat()}: {fetch_err}")
                continue

        if not raw_records:
            logger.warning("⚠️  Pichhle 4 din me koi bhi data available nahi hai. Skip.")
            return

        # Clean
        cleaned, clean_skipped = clean_records(raw_records)
        logger.info(f"Cleaned: {len(cleaned)} (skipped {clean_skipped})")

        # Validate
        valid, invalid = validate_records(cleaned)
        logger.info(f"Validated: {len(valid)} (invalid {len(invalid)})")

        # Save
        result = save_records(
            records=valid,
            sync_date=target_date.isoformat(),
            records_fetched=len(raw_records),
            duplicates_prechecked=0,
            invalid_count=len(invalid) + clean_skipped,
        )

        logger.info(
            f"💾 Daily fetch DONE: "
            f"date={target_date.isoformat()}, "
            f"inserted={result['inserted']}, "
            f"skipped={result['skipped']}, "
            f"errors={result['errors']}"
        )

    except Exception as e:
        logger.exception(f"❌ Daily fetch job failed: {e}")


# ============================================================
# SECTION 2: START SCHEDULER
# ============================================================

def start_scheduler() -> BackgroundScheduler:
    """
    Background scheduler start karta hai.

    Flask app ke saath ek hi process me chalta hai.
    Daily fetch job schedule hoti hai.

    Returns:
        BackgroundScheduler instance.
    """
    global _scheduler

    # Agar pehle se chal raha hai to wahi return karo
    if _scheduler is not None and _scheduler.running:
        logger.info("Scheduler already running.")
        return _scheduler

    # Naya scheduler banao
    _scheduler = BackgroundScheduler(
        timezone="Asia/Kolkata",   # IST timezone
        job_defaults={
            "coalesce": True,       # Missed jobs ko merge karo
            "max_instances": 1,     # Ek waqt me ek hi instance
            "misfire_grace_time": 3600,  # 1 ghante tak late chalne do
        },
    )

    # --------------------------------------------------------
    # DAILY FETCH JOB
    # --------------------------------------------------------
    hour = GovernmentAPIConfig.DAILY_FETCH_HOUR
    minute = GovernmentAPIConfig.DAILY_FETCH_MINUTE

    _scheduler.add_job(
        _daily_fetch_job,
        trigger=CronTrigger(hour=hour, minute=minute),
        id="daily_mandi_fetch",
        name="Daily Mandi Data Fetch",
        replace_existing=True,
    )

    logger.info(
        f"✅ Daily fetch job scheduled at {hour:02d}:{minute:02d} IST daily"
    )

    # Scheduler start karo
    _scheduler.start()
    logger.info("✅ Background scheduler started")

    return _scheduler


def stop_scheduler():
    """Scheduler ko gracefully stop karta hai."""
    global _scheduler
    if _scheduler is not None and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("🛑 Scheduler stopped")
        _scheduler = None


def get_scheduler_status() -> dict:
    """
    Scheduler ka status return karta hai (dashboard/health check ke liye).

    Returns:
        dict: {
            "running": bool,
            "jobs": [{id, name, next_run_time}, ...]
        }
    """
    if _scheduler is None or not _scheduler.running:
        return {"running": False, "jobs": []}

    jobs = []
    for job in _scheduler.get_jobs():
        jobs.append({
            "id": job.id,
            "name": job.name,
            "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
        })

    return {
        "running": True,
        "jobs": jobs,
    }


# ============================================================
# SECTION 3: DIRECT RUN — Test / Manual Trigger
# ============================================================

if __name__ == "__main__":
    print("=" * 65)
    print("KisanBazaar AI — Scheduler Test")
    print("=" * 65)

    print("\nOptions:")
    print("  1. Scheduler start karke wait karo (Ctrl+C to stop)")
    print("  2. Immediately daily fetch job manually chalao")
    print()

    choice = input("Choose (1/2): ").strip() or "1"

    if choice == "2":
        # Manual trigger
        print("\n🔧 Manually running daily fetch job...\n")
        _daily_fetch_job()
        print("\n✅ Manual job complete.")
    else:
        # Scheduler start karo
        print(f"\nScheduler start kar rahe hain...")
        print(f"Daily job time: {GovernmentAPIConfig.DAILY_FETCH_HOUR:02d}:"
              f"{GovernmentAPIConfig.DAILY_FETCH_MINUTE:02d} IST")
        print("Ctrl+C dabao stop karne ke liye.\n")

        sched = start_scheduler()

        # Status print karo
        status = get_scheduler_status()
        print(f"Scheduler running: {status['running']}")
        for job in status["jobs"]:
            print(f"  Job: {job['name']} (id={job['id']})")
            print(f"  Next run: {job['next_run']}")

        # Wait loop
        try:
            while True:
                time.sleep(60)
        except KeyboardInterrupt:
            print("\n\n🛑 Stopping scheduler...")
            stop_scheduler()
            print("Done.")