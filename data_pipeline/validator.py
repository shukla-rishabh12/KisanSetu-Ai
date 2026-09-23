# ============================================================
# KisanBazaar AI — Data Validator
# ============================================================
# Ye file CLEANED records pe strict validation karti hai.
# Cleaner format theek karta hai, validator business rules lagata hai.
#
# KYA VALIDATE KARTA HAI:
#   1. Date validation — future date nahi, 2 saal se purana nahi
#   2. Price validation — realistic range (1 se 1,00,000)
#   3. Sanity check — min ≤ modal ≤ max
#   4. Duplicate detection — batch ke andar
#   5. Required field completeness
#
# RETURNS:
#   (valid_records, invalid_records)
#   - valid_records → aage database_loader ko
#   - invalid_records → log karke skip (debugging ke liye)
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
from core.logger import get_logger

# Logger
logger = get_logger(__name__)


# ============================================================
# SECTION 1: VALIDATION RULES (Constants)
# ============================================================
# In values ko badal kar rules tweak kar sakte ho.

# Price range — realistic mandi prices (₹ per quintal typically)
MIN_REASONABLE_PRICE = 1.0          # ₹1 se kam koi price nahi
MAX_REASONABLE_PRICE = 100000.0     # ₹1 lakh se zyada suspicious

# Date range — kitna purana data allowed hai
MAX_DAYS_IN_FUTURE = 0              # Future date allowed nahi (0 = aaj tak)
MAX_DAYS_IN_PAST = 365 * DatabaseConfig.RETENTION_YEARS  # 2 saal

# Required fields jo har record me hone chahiye
REQUIRED_FIELDS = ["state", "market", "commodity", "arrival_date", "modal_price"]


# ============================================================
# SECTION 2: DATE VALIDATION
# ============================================================

def _validate_date(arrival_date_str: str) -> tuple[bool, str]:
    """
    Date valid hai ya nahi check karta hai.

    Rules:
      - Format YYYY-MM-DD hona chahiye
      - Future date nahi hona chahiye
      - 2 saal se purani date nahi hona chahiye

    Returns:
        tuple: (is_valid, reason_if_invalid)
    """
    if not arrival_date_str:
        return False, "date missing"

    try:
        parsed_date = datetime.strptime(arrival_date_str, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return False, f"invalid date format: {arrival_date_str}"

    today = date.today()

    # Future date check
    if parsed_date > today + timedelta(days=MAX_DAYS_IN_FUTURE):
        return False, f"future date: {arrival_date_str}"

    # Purani date check
    cutoff = today - timedelta(days=MAX_DAYS_IN_PAST)
    if parsed_date < cutoff:
        return False, f"date purani hai (>{MAX_DAYS_IN_PAST} days): {arrival_date_str}"

    return True, ""


# ============================================================
# SECTION 3: PRICE VALIDATION
# ============================================================

def _validate_prices(record: dict) -> tuple[bool, str]:
    """
    Price fields (min, modal, max) valid hain ya nahi.

    Rules:
      - Modal price required hai
      - Saare prices positive hone chahiye
      - Prices realistic range me hone chahiye
      - min ≤ modal ≤ max (usually)

    Returns:
        tuple: (is_valid, reason_if_invalid)
    """
    modal = record.get("modal_price")
    min_p = record.get("min_price")
    max_p = record.get("max_price")

    # Modal price mandatory
    if modal is None:
        return False, "modal_price missing"

    # Range check for each present price
    for name, val in [("modal_price", modal), ("min_price", min_p), ("max_price", max_p)]:
        if val is None:
            continue
        if val < MIN_REASONABLE_PRICE:
            return False, f"{name} too low: {val}"
        if val > MAX_REASONABLE_PRICE:
            return False, f"{name} too high: {val}"

    # Sanity: min ≤ modal ≤ max
    # NOTE: Hum strict nahi hain yahan. Agar ye rule fail ho to
    # sirf WARN karenge, reject nahi karenge. Kyunki real mandi data
    # me occasionally aisa hota hai.
    if min_p is not None and modal is not None and min_p > modal:
        logger.debug(
            f"Sanity warn (min > modal): market={record.get('market')}, "
            f"date={record.get('arrival_date')}, min={min_p}, modal={modal}"
        )
    if max_p is not None and modal is not None and modal > max_p:
        logger.debug(
            f"Sanity warn (modal > max): market={record.get('market')}, "
            f"date={record.get('arrival_date')}, modal={modal}, max={max_p}"
        )

    return True, ""


# ============================================================
# SECTION 4: REQUIRED FIELDS VALIDATION
# ============================================================

def _validate_required(record: dict) -> tuple[bool, str]:
    """
    Required fields present hain ya nahi check karta hai.
    """
    for field in REQUIRED_FIELDS:
        if not record.get(field):
            return False, f"required field missing: {field}"
    return True, ""


# ============================================================
# SECTION 5: SINGLE RECORD VALIDATION
# ============================================================

def validate_record(record: dict) -> tuple[bool, str]:
    """
    Ek cleaned record ko validate karta hai.

    Args:
        record: Cleaner se aaya hua clean record.

    Returns:
        tuple: (is_valid, reason_if_invalid)

    Example:
        valid, reason = validate_record(cleaned)
        if not valid:
            print(f"Skip: {reason}")
    """
    if not isinstance(record, dict):
        return False, "record dict nahi hai"

    # 1. Required fields
    ok, reason = _validate_required(record)
    if not ok:
        return False, reason

    # 2. Date
    ok, reason = _validate_date(record.get("arrival_date"))
    if not ok:
        return False, reason

    # 3. Prices
    ok, reason = _validate_prices(record)
    if not ok:
        return False, reason

    return True, ""


# ============================================================
# SECTION 6: DEDUPLICATION WITHIN BATCH
# ============================================================

def _make_unique_key(record: dict) -> tuple:
    """
    Ek record ke liye unique key banata hai (duplicate detection ke liye).

    Key: (state, district, market, commodity, variety, grade, arrival_date)
    Ye schema ke UNIQUE constraint se match karta hai.
    """
    return (
        (record.get("state") or "").lower().strip(),
        (record.get("district") or "").lower().strip(),
        (record.get("market") or "").lower().strip(),
        (record.get("commodity") or "").lower().strip(),
        (record.get("variety") or "").lower().strip(),
        (record.get("grade") or "").lower().strip(),
        record.get("arrival_date") or "",
    )


# ============================================================
# SECTION 7: BATCH VALIDATION
# ============================================================

def validate_records(records: list[dict]) -> tuple[list[dict], list[dict]]:
    """
    Ek batch ke cleaned records ko validate karta hai.

    Steps:
      1. Har record pe validate_record() chalao
      2. Batch ke andar duplicates hatao
      3. Valid aur invalid records alag karo

    Args:
        records: Cleaned records ki list.

    Returns:
        tuple: (valid_records, invalid_records)
               - valid_records: DB me insert karne ke liye ready
               - invalid_records: Skip karne wale (reason ke saath)

    Example:
        valid, invalid = validate_records(cleaned_batch)
        print(f"Valid: {len(valid)}, Invalid: {len(invalid)}")
    """
    if not records:
        return [], []

    logger.info(f"Validating batch: {len(records)} records")

    valid_records = []
    invalid_records = []
    seen_keys = set()
    duplicates_in_batch = 0

    for idx, record in enumerate(records):
        # 1. Validate karo
        is_valid, reason = validate_record(record)

        if not is_valid:
            # Invalid — reason ke saath log karo
            invalid_records.append({
                "record": record,
                "reason": reason,
            })
            logger.debug(f"Record #{idx} invalid: {reason}")
            continue

        # 2. Batch ke andar duplicate check
        key = _make_unique_key(record)
        if key in seen_keys:
            duplicates_in_batch += 1
            logger.debug(
                f"Record #{idx} duplicate within batch: "
                f"{record.get('market')} | {record.get('commodity')} | "
                f"{record.get('arrival_date')}"
            )
            continue

        seen_keys.add(key)
        valid_records.append(record)

    # Summary log
    logger.info(
        f"✅ Validation done: "
        f"{len(valid_records)} valid, "
        f"{len(invalid_records)} invalid, "
        f"{duplicates_in_batch} duplicates (within batch)"
    )

    return valid_records, invalid_records


# ============================================================
# SECTION 8: DIRECT RUN — Quick Test
# ============================================================
if __name__ == "__main__":
    from datetime import date, timedelta

    print("=" * 60)
    print("KisanBazaar AI — Data Validator Test")
    print("=" * 60)

    today_str = date.today().strftime("%Y-%m-%d")
    future_str = (date.today() + timedelta(days=10)).strftime("%Y-%m-%d")
    old_str = (date.today() - timedelta(days=1000)).strftime("%Y-%m-%d")

    # Test 1: Valid record
    print("\n--- Test 1: Valid record ---")
    record_valid = {
        "state": "Uttar Pradesh",
        "district": "Kanpur Nagar",
        "market": "Kanpur",
        "commodity": "Potato",
        "variety": "Jyoti",
        "grade": None,
        "arrival_date": today_str,
        "min_price": 2500.0,
        "max_price": 3000.0,
        "modal_price": 2750.0,
    }
    ok, reason = validate_record(record_valid)
    print(f"Valid? {ok} | Reason: {reason}")

    # Test 2: Future date
    print("\n--- Test 2: Future date ---")
    record_future = {**record_valid, "arrival_date": future_str}
    ok, reason = validate_record(record_future)
    print(f"Valid? {ok} | Reason: {reason}")

    # Test 3: Old date (2 saal se purani)
    print("\n--- Test 3: Very old date ---")
    record_old = {**record_valid, "arrival_date": old_str}
    ok, reason = validate_record(record_old)
    print(f"Valid? {ok} | Reason: {reason}")

    # Test 4: Missing modal price
    print("\n--- Test 4: Missing modal price ---")
    record_no_modal = {**record_valid, "modal_price": None}
    ok, reason = validate_record(record_no_modal)
    print(f"Valid? {ok} | Reason: {reason}")

    # Test 5: Unrealistic price
    print("\n--- Test 5: Unrealistic price ---")
    record_huge = {**record_valid, "modal_price": 999999.0}
    ok, reason = validate_record(record_huge)
    print(f"Valid? {ok} | Reason: {reason}")

    # Test 6: Batch validation (with duplicates)
    print("\n--- Test 6: Batch validation ---")
    batch = [
        record_valid,                              # valid
        {**record_valid},                          # duplicate (same as #1)
        record_future,                             # invalid (future)
        {**record_valid, "modal_price": None},     # invalid (missing modal)
        {**record_valid, "market": "Lucknow"},     # valid (different market)
    ]
    valid, invalid = validate_records(batch)
    print(f"\nInput : {len(batch)} records")
    print(f"Valid : {len(valid)}")
    print(f"Invalid: {len(invalid)}")
    for inv in invalid:
        print(f"  - {inv['reason']}")

    print("\n" + "=" * 60)
    print("✅ Validator test complete.")