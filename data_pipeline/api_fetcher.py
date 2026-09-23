# ============================================================
# KisanBazaar AI — Government Mandi API Fetcher
# ============================================================
# Ye file data.gov.in ke Mandi Price API se data fetch karti hai.
#
# Features:
#   1. Date-aware fetch — kisi bhi date ka data
#   2. Pagination (offset + limit) — saare records
#   3. Retry with exponential backoff
#   4. Timeout handling
#   5. Config se API key, resource ID, settings
#   6. Logging har step pe
#   7. Custom exceptions raise karti hai
#
# API DETAILS (SRS ke hisaab se):
#   Resource ID: 35985678-0d79-46b4-9ed6-6f13308a1d24
#   Date format for filter: DD/MM/YYYY
#   Response format: JSON
#   Pagination: limit=2000, offset increments
#
# USAGE:
#   from data_pipeline.api_fetcher import fetch_data_for_date
#   records = fetch_data_for_date(date(2026, 9, 15))
# ============================================================

import sys
import time
from datetime import date, datetime, timedelta   # ← timedelta add kiya
from pathlib import Path
from typing import Optional

# ------------------------------------------------------------
# PATH FIX: Project root ko sys.path me add karo.
# Isse file direct run karne pe bhi imports kaam karein.
# ------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# Third-party
import requests

# Project imports
from config import GovernmentAPIConfig
from core.logger import get_logger
from core.exceptions import (
    DataFetchError,
    APIError,
    ConfigurationError,
)

# Logger
logger = get_logger(__name__)


# ============================================================
# SECTION 1: VALIDATION HELPERS
# ============================================================

def _validate_config() -> None:
    """
    API key aur zaroori config check karta hai.
    Agar API key missing hai to ConfigurationError raise karo.
    """
    if not GovernmentAPIConfig.API_KEY:
        raise ConfigurationError(
            "Government API key missing hai. "
            ".env file me GOVT_API_KEY set karo.",
            details={"env_var": "GOVT_API_KEY"},
        )

    if not GovernmentAPIConfig.BASE_URL:
        raise ConfigurationError(
            "API Base URL missing hai. config.py check karo."
        )


def _format_date_for_api(target_date: date) -> str:
    """
    Python date object ko API ke expected format (DD/MM/YYYY) me convert karta hai.
    """
    return target_date.strftime("%d/%m/%Y")


# ============================================================
# SECTION 2: SINGLE API REQUEST (with retry)
# ============================================================

def _make_request(
    target_date: date,
    offset: int,
) -> dict:
    """
    Ek single API request bhejta hai (ek page) aur JSON response return karta hai.

    Retry logic:
      - MAX_RETRIES attempts
      - Har attempt ke beech wait badhta hai (exponential backoff)
      - Har attempt ka log

    Args:
        target_date: Kis date ka data chahiye.
        offset: Pagination offset (0, 2000, 4000, ...).

    Returns:
        dict: API ka JSON response (records, total, etc.).

    Raises:
        APIError: Agar saare retries fail ho gaye.
    """
    # API key aur base URL verify
    _validate_config()

    # API ko bhejne ke liye date string (DD/MM/YYYY)
    date_string = _format_date_for_api(target_date)

    # Query parameters — SRS ke hisaab se
    params = {
        "api-key": GovernmentAPIConfig.API_KEY,
        "format": GovernmentAPIConfig.FORMAT,
        "limit": GovernmentAPIConfig.CHUNK_SIZE,
        "offset": offset,
        "filters[Arrival_Date]": date_string,
    }

    # Retry loop
    last_exception = None
    for attempt in range(1, GovernmentAPIConfig.MAX_RETRIES + 1):
        try:
            logger.debug(
                f"API request: date={date_string}, offset={offset}, "
                f"attempt={attempt}/{GovernmentAPIConfig.MAX_RETRIES}"
            )

            # Request bhejo
            response = requests.get(
                GovernmentAPIConfig.BASE_URL,
                params=params,
                timeout=GovernmentAPIConfig.REQUEST_TIMEOUT,
                headers={
                    "User-Agent": "KisanBazaar-AI/1.0",
                    "Accept": "application/json",
                },
            )

            # HTTP status check
            if response.status_code != 200:
                raise APIError(
                    f"API ne {response.status_code} status diya",
                    status_code=response.status_code,
                    details={
                        "date": date_string,
                        "offset": offset,
                        "response_text": response.text[:200],  # first 200 chars
                    },
                )

            # JSON parse
            try:
                data = response.json()
            except ValueError as e:
                raise APIError(
                    f"API response JSON nahi hai: {e}",
                    details={
                        "date": date_string,
                        "offset": offset,
                        "response_text": response.text[:200],
                    },
                )

            # Success
            logger.debug(
                f"API success: date={date_string}, offset={offset}, "
                f"records={len(data.get('records', []))}, total={data.get('total', 0)}"
            )
            return data

        except (requests.exceptions.RequestException, APIError) as e:
            last_exception = e
            logger.warning(
                f"API attempt {attempt}/{GovernmentAPIConfig.MAX_RETRIES} failed: {e}"
            )

            # Agar aur attempts bache hain to wait karo
            if attempt < GovernmentAPIConfig.MAX_RETRIES:
                wait_time = GovernmentAPIConfig.RETRY_BACKOFF * attempt
                logger.info(f"Retrying after {wait_time} seconds...")
                time.sleep(wait_time)

    # Saare retries fail
    raise DataFetchError(
        f"API request {GovernmentAPIConfig.MAX_RETRIES} attempts ke baad bhi fail hui",
        details={
            "date": date_string,
            "offset": offset,
            "last_error": str(last_exception),
        },
    )


# ============================================================
# SECTION 3: FETCH ALL PAGES FOR A DATE
# ============================================================

def fetch_data_for_date(target_date: date) -> list[dict]:
    """
    Ek specific date ke saare records fetch karta hai (pagination ke saath).

    Flow:
      1. Offset = 0 se start
      2. API se chunk fetch (2000 records)
      3. Records collect karo
      4. Agar total records mil gaye to stop
      5. Warna offset badhao aur repeat
      6. Chhota wait between requests (API ko overload na karein)

    Args:
        target_date: Kis date ka data chahiye.

    Returns:
        list[dict]: Saare raw records (API ke original field names ke saath).

    Raises:
        DataFetchError: Agar API fail ho ya koi network issue ho.
    """
    logger.info(f"Fetching data for date: {target_date.isoformat()}")

    all_records = []
    offset = 0
    total_available = None  # API ke response se pata chalega

    while True:
        # Ek page fetch karo (retry ke saath)
        data = _make_request(target_date, offset)

        # Records nikalo
        records = data.get("records", [])
        api_total = int(data.get("total", 0))

        # Pehli baar total pata chala
        if total_available is None:
            total_available = api_total
            logger.info(
                f"API total records for {target_date.isoformat()}: {total_available}"
            )

        # Agar is page pe koi record nahi aaya, to ruk jao
        if not records:
            logger.debug(f"No more records at offset {offset}. Stopping.")
            break

        # Records collect karo
        all_records.extend(records)
        logger.debug(
            f"Fetched {len(records)} records at offset {offset}. "
            f"Total so far: {len(all_records)}"
        )

        # Check karo ki saare records mil gaye ya nahi
        if len(all_records) >= total_available:
            logger.debug(
                f"All {total_available} records fetched for {target_date.isoformat()}"
            )
            break

        # Next page ke liye offset badhao
        offset += GovernmentAPIConfig.CHUNK_SIZE

        # API ko thoda rest do (rate limit avoid karne ke liye)
        time.sleep(0.5)

    logger.info(
        f"✅ Total {len(all_records)} records fetched for {target_date.isoformat()}"
    )
    return all_records


# ============================================================
# SECTION 4: FETCH LATEST AVAILABLE DATE (Optional helper)
# ============================================================

def fetch_data_for_latest_date() -> tuple[date, list[dict]]:
    """
    Aaj ya kal ka data fetch karne ki koshish karta hai.
    Government API usually 1-2 din purana data deta hai.

    Returns:
        tuple: (actual_date, records)
    """
    # Aaj se 2 din pehle tak try karo
    for days_ago in range(0, 4):
        target = date.today() - timedelta(days=days_ago)
        try:
            records = fetch_data_for_date(target)
            if records:
                logger.info(f"Latest data mila: {target.isoformat()}")
                return target, records
        except DataFetchError as e:
            logger.warning(f"Date {target.isoformat()} pe data nahi mila: {e}")
            continue

    raise DataFetchError("Pichhle 4 din me koi bhi data available nahi hai.")


# ============================================================
# SECTION 5: DIRECT RUN — Quick Test
# ============================================================
if __name__ == "__main__":
    print("=" * 60)
    print("KisanBazaar AI — API Fetcher Test")
    print("=" * 60)

    # Test date — pichhle hafte ki koi date (data available hone chahiye)
    test_date = date.today() - timedelta(days=7)
    print(f"\nTest date: {test_date.isoformat()}")

    try:
        records = fetch_data_for_date(test_date)

        print(f"\n✅ Records fetched: {len(records)}")

        if records:
            print("\n--- Sample Record (first one) ---")
            sample = records[0]
            for key, value in list(sample.items())[:12]:  # first 12 fields
                print(f"  {key}: {value}")
        else:
            print("⚠️  Is date pe koi record nahi mila. Doosri date try karo.")

    except ConfigurationError as e:
        print(f"\n❌ Configuration Error: {e}")
        print("   .env file me GOVT_API_KEY set karo.")
    except DataFetchError as e:
        print(f"\n❌ Data Fetch Error: {e}")
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")

    print("\n" + "=" * 60)