# ============================================================
# KisanBazaar AI — Data Cleaner
# ============================================================
# Ye file API se aaye raw records ko clean karke SQLite-ready
# format me convert karti hai.
#
# KYA CLEAN KARTA HAI:
#   1. Arrival_Date: DD/MM/YYYY → YYYY-MM-DD (SRS requirement)
#   2. String fields: whitespace trim, empty → None
#   3. Price fields: string → float (numeric)
#   4. Field names: API format → database column names
#      (Arrival_Date → arrival_date, State → state, etc.)
#   5. Invalid records skip (log karke)
#
# IMPORTANT:
#   - Kabhi bhi missing price ko 0 nahi karenge. SRS me clearly
#     likha hai: "0 price ≠ missing price".
#   - Invalid records ko quarantine karenge (skip + log),
#     pura batch fail nahi karenge.
# ============================================================

import sys
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

# ------------------------------------------------------------
# PATH FIX: Project root ko sys.path me add karo.
# ------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# Project imports
from core.logger import get_logger
from core.exceptions import DataCleanError, DataValidationError

# Logger
logger = get_logger(__name__)


# ============================================================
# SECTION 1: FIELD NAME MAPPING
# ============================================================
# API ke field names → SQLite column names
# (SRS me likha hai: "Column Names Standardize")
# ============================================================

FIELD_MAP = {
    "Arrival_Date": "arrival_date",
    "State":        "state",
    "District":     "district",
    "Market":       "market",
    "Commodity":    "commodity",
    "Variety":      "variety",
    "Grade":        "grade",
    "Min_Price":    "min_price",
    "Max_Price":    "max_price",
    "Modal_Price":  "modal_price",
}

# Kaunse fields numeric hone chahiye
NUMERIC_FIELDS = {"min_price", "max_price", "modal_price"}

# Kaunse fields mandatory hain (inme se koi bhi missing → record skip)
REQUIRED_FIELDS = {"state", "market", "commodity", "arrival_date"}


# ============================================================
# SECTION 2: HELPER — SAFE STRING
# ============================================================

def _clean_string(value) -> str:
    """
    String value ko clean karta hai:
      - None ya empty → "" (empty string)
      - Whitespace trim
      - Multiple spaces ko single space me convert

    IMPORTANT: None ki jagah "" return kar rahe hain kyunki
    SQLite me NULL values UNIQUE constraint me hamesha different
    maani jaati hain. Isse duplicate detection fail ho jaati hai.
    "" (empty string) use karne se duplicate detection sahi kaam karta hai.

    Example:
        "  Kanpur  " → "Kanpur"
        "Uttar  Pradesh" → "Uttar Pradesh"
        ""  → ""
        None → ""
    """
    if value is None:
        return ""

    # String me convert karo
    text = str(value).strip()

    # Empty ho gaya to ""
    if not text:
        return ""

    # Multiple spaces ko single space karo
    text = re.sub(r"\s+", " ", text)

    return text


# ============================================================
# SECTION 3: HELPER — SAFE FLOAT
# ============================================================

def _clean_float(value) -> Optional[float]:
    """
    Price value ko safe tarike se float me convert karta hai.

    Rules:
      - None ya empty → None (0 NAHI karenge!)
      - String me comma ho to hatao ("2,750" → "2750")
      - Negative values ko reject karo (None return karo)
      - Conversion fail ho to None

    Example:
        "2750" → 2750.0
        "2,750.50" → 2750.5
        "" → None
        None → None
        "-500" → None (invalid)
        "abc" → None (invalid)
    """
    if value is None:
        return None

    # Agar already number hai
    if isinstance(value, (int, float)):
        # Negative price invalid
        if value < 0:
            return None
        return float(value)

    # String → clean
    text = str(value).strip()

    if not text:
        return None

    # Comma hatao ("2,750" → "2750")
    text = text.replace(",", "")

    # Numeric conversion try karo
    try:
        num = float(text)
        # Negative price invalid
        if num < 0:
            return None
        return num
    except (ValueError, TypeError):
        return None


# ============================================================
# SECTION 4: HELPER — DATE CONVERSION
# ============================================================

def _clean_date(value) -> Optional[str]:
    """
    Date ko DD/MM/YYYY se YYYY-MM-DD me convert karta hai (SRS requirement).

    Multiple formats support karta hai (safety ke liye):
      - DD/MM/YYYY  (API ka standard format)
      - DD-MM-YYYY
      - YYYY-MM-DD  (already clean)

    Example:
        "13/09/2026" → "2026-09-13"
        "13-09-2026" → "2026-09-13"
        "2026-09-13" → "2026-09-13"
        "" → None
        "abc" → None
    """
    if value is None:
        return None

    text = str(value).strip()
    if not text:
        return None

    # Try multiple formats
    formats_to_try = [
        "%d/%m/%Y",   # DD/MM/YYYY (API standard)
        "%d-%m-%Y",   # DD-MM-YYYY
        "%Y-%m-%d",   # YYYY-MM-DD (already normalized)
    ]

    for fmt in formats_to_try:
        try:
            parsed = datetime.strptime(text, fmt)
            # Output in YYYY-MM-DD
            return parsed.strftime("%Y-%m-%d")
        except ValueError:
            continue

    # Koi format match nahi hua
    return None


# ============================================================
# SECTION 5: MAIN CLEAN FUNCTION — SINGLE RECORD
# ============================================================

def clean_record(raw: dict) -> Optional[dict]:
    """
    Ek raw API record ko clean karke SQLite-ready dict return karta hai.

    Args:
        raw: API ka original record (dict).

    Returns:
        dict: Cleaned record (SQLite-ready) — ya None agar record
              invalid hai (jaise date missing ya required field missing).

    Example:
        Input:
            {
                "Arrival_Date": "13/09/2026",
                "State": "  Uttar Pradesh  ",
                "Market": "Kanpur",
                "Commodity": "Potato",
                "Variety": "Jyoti",
                "Min_Price": "2500",
                "Max_Price": "3000",
                "Modal_Price": "2750"
            }

        Output:
            {
                "arrival_date": "2026-09-13",
                "state": "Uttar Pradesh",
                "market": "Kanpur",
                "commodity": "Potato",
                "variety": "Jyoti",
                "grade": None,
                "district": None,
                "min_price": 2500.0,
                "max_price": 3000.0,
                "modal_price": 2750.0,
                "source": "government_api"
            }
    """
    if not isinstance(raw, dict):
        return None

    cleaned = {}

    # --------------------------------------------------------
    # STEP 1: Field names map karo + clean karo
    # --------------------------------------------------------
    for api_field, db_field in FIELD_MAP.items():
        raw_value = raw.get(api_field)

        if db_field == "arrival_date":
            # Date special handling
            cleaned[db_field] = _clean_date(raw_value)
        elif db_field in NUMERIC_FIELDS:
            # Price fields — numeric
            cleaned[db_field] = _clean_float(raw_value)
        else:
            # String fields
            cleaned[db_field] = _clean_string(raw_value)

    # --------------------------------------------------------
    # STEP 2: Required fields check karo
    # --------------------------------------------------------
    # Agar koi bhi required field missing hai to record skip.
    # Example: date invalid, market missing, commodity missing.
    missing = [f for f in REQUIRED_FIELDS if not cleaned.get(f)]
    if missing:
        logger.debug(
            f"Record skipped (missing required fields: {missing}): "
            f"raw={raw}"
        )
        return None

    # --------------------------------------------------------
    # STEP 3: Modal price at least ek price hona chahiye
    # --------------------------------------------------------
    # Agar teeno prices missing hain to record se kya fayda?
    # Modal price primary target hai, uske bina record useless hai.
    if cleaned.get("modal_price") is None:
        logger.debug(
            f"Record skipped (modal_price missing): "
            f"market={cleaned.get('market')}, "
            f"date={cleaned.get('arrival_date')}"
        )
        return None

    # --------------------------------------------------------
    # STEP 4: Logical sanity checks
    # --------------------------------------------------------
    # Min <= Modal <= Max hona chahiye (usually). Agar nahi hai to
    # ye suspicious record hai — lekin hum skip nahi karenge,
    # sirf warn karenge. Kuch markets me unusual patterns hote hain.
    min_p = cleaned.get("min_price")
    max_p = cleaned.get("max_price")
    mod_p = cleaned.get("modal_price")

    if min_p is not None and max_p is not None and min_p > max_p:
        logger.warning(
            f"Suspicious record (min > max): market={cleaned.get('market')}, "
            f"date={cleaned.get('arrival_date')}, min={min_p}, max={max_p}"
        )

    if min_p is not None and mod_p is not None and mod_p < min_p:
        logger.warning(
            f"Suspicious record (modal < min): market={cleaned.get('market')}, "
            f"date={cleaned.get('arrival_date')}, modal={mod_p}, min={min_p}"
        )

    if max_p is not None and mod_p is not None and mod_p > max_p:
        logger.warning(
            f"Suspicious record (modal > max): market={cleaned.get('market')}, "
            f"date={cleaned.get('arrival_date')}, modal={mod_p}, max={max_p}"
        )

    # --------------------------------------------------------
    # STEP 5: Source add karo (debugging ke liye useful)
    # --------------------------------------------------------
    cleaned["source"] = "government_api"

    return cleaned


# ============================================================
# SECTION 6: MAIN CLEAN FUNCTION — BATCH
# ============================================================

def clean_records(raw_records: list[dict]) -> tuple[list[dict], int]:
    """
    Ek batch ke records ko clean karta hai.

    Args:
        raw_records: API se aaye raw records ki list.

    Returns:
        tuple: (cleaned_records, skipped_count)
               - cleaned_records: SQLite-ready dicts
               - skipped_count: Kitne records skip hue

    Example:
        cleaned, skipped = clean_records(raw_records)
        print(f"Cleaned: {len(cleaned)}, Skipped: {skipped}")
    """
    if not raw_records:
        return [], 0

    logger.info(f"Cleaning batch: {len(raw_records)} records")

    cleaned_list = []
    skipped = 0

    for idx, raw in enumerate(raw_records):
        try:
            result = clean_record(raw)
            if result is not None:
                cleaned_list.append(result)
            else:
                skipped += 1
        except Exception as e:
            # Individual record pe unexpected error — pura batch fail nahi karenge
            logger.warning(f"Record #{idx} cleaning failed: {e}")
            skipped += 1

    logger.info(
        f"✅ Cleaning done: {len(cleaned_list)} clean, {skipped} skipped"
    )
    return cleaned_list, skipped


# ============================================================
# SECTION 7: DIRECT RUN — Quick Test
# ============================================================
if __name__ == "__main__":
    print("=" * 60)
    print("KisanBazaar AI — Data Cleaner Test")
    print("=" * 60)

    # Test 1: Valid record
    print("\n--- Test 1: Valid record ---")
    raw1 = {
        "Arrival_Date": "13/09/2026",
        "State": "  Uttar Pradesh  ",
        "District": "Kanpur Nagar",
        "Market": "Kanpur",
        "Commodity": "Potato",
        "Variety": "Jyoti",
        "Min_Price": "2500",
        "Max_Price": "3,000",
        "Modal_Price": "2750",
    }
    cleaned1 = clean_record(raw1)
    print(f"Input : {raw1}")
    print(f"Output: {cleaned1}")

    # Test 2: Missing date
    print("\n--- Test 2: Missing date ---")
    raw2 = {
        "Arrival_Date": "",
        "State": "Uttar Pradesh",
        "Market": "Kanpur",
        "Commodity": "Potato",
        "Modal_Price": "2750",
    }
    cleaned2 = clean_record(raw2)
    print(f"Input : {raw2}")
    print(f"Output: {cleaned2} (should be None)")

    # Test 3: Negative price (invalid)
    print("\n--- Test 3: Negative price ---")
    raw3 = {
        "Arrival_Date": "13/09/2026",
        "State": "Uttar Pradesh",
        "Market": "Kanpur",
        "Commodity": "Potato",
        "Modal_Price": "-500",
    }
    cleaned3 = clean_record(raw3)
    print(f"Input : {raw3}")
    print(f"Output: {cleaned3} (should be None because modal_price invalid)")

    # Test 4: Missing modal price
    print("\n--- Test 4: Missing modal price ---")
    raw4 = {
        "Arrival_Date": "13/09/2026",
        "State": "Uttar Pradesh",
        "Market": "Kanpur",
        "Commodity": "Potato",
        "Modal_Price": "",
    }
    cleaned4 = clean_record(raw4)
    print(f"Input : {raw4}")
    print(f"Output: {cleaned4} (should be None)")

    # Test 5: Batch clean
    print("\n--- Test 5: Batch clean ---")
    batch = [raw1, raw2, raw3, raw4]
    cleaned_batch, skipped = clean_records(batch)
    print(f"Input : {len(batch)} records")
    print(f"Output: {len(cleaned_batch)} clean, {skipped} skipped")

    print("\n" + "=" * 60)
    print("✅ Cleaner test complete.")