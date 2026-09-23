# ============================================================
# KisanBazaar AI — ML Services (Business Logic)
# ============================================================
# Ye file ML prediction ke liye orchestrator hai.
# Routes iske through kaam karte hain.
#
# KAAM:
#   1. Input validation (sab required fields)
#   2. Historical data check (enough records?)
#   3. Prediction call (predict.py se)
#   4. Expected gross value calculation (with unit conversion)
#   5. Prediction logging (prediction_logs table)
#
# IMPORTANT — Unit Conversion:
#   DB me prices ₹/quintal me hain (government source).
#   User quantity kg me deta hai (farmer convention).
#   1 quintal = 100 kg
#   Expected value = (quantity_kg / 100) * modal_price_per_quintal
# ============================================================

import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

# ------------------------------------------------------------
# PATH FIX
# ------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# Project imports
from ml.predict import predict_for_date, forecast_next_days, _load_model
from database.db import fetch_one, fetch_all, execute_query, count_rows
from core.logger import get_logger
from core.exceptions import PredictionError, ModelNotFoundError

# Logger
logger = get_logger(__name__)


# ============================================================
# SECTION 1: CONSTANTS
# ============================================================

QUINTAL_TO_KG = 100.0  # 1 quintal = 100 kg

# Minimum records needed for reliable prediction
# (model ke lag_90 aur roll_30 ke liye minimum 90+ chahiye)
MIN_RECORDS_WARNING = 30   # below this, warning
MIN_RECORDS_STRICT = 0    # below this, reject

# ============================================================
# SECTION 2: DATA AVAILABILITY CHECK
# ============================================================

def check_data_availability(
    market: str,
    commodity: str,
    variety: Optional[str] = None,
) -> dict:
    """
    Check karta hai ki market+commodity+variety ka data available hai.
    
    Returns:
        dict: {
            "available": bool,
            "record_count": int,
            "date_range": {"min": ..., "max": ...},
            "warning": str or None
        }
    """
    where = "market = ? AND commodity = ?"
    params = [market, commodity]
    
    if variety:
        where += " AND variety = ?"
        params.append(variety)
    
    row = fetch_one(
        f"""
        SELECT COUNT(*) as cnt,
               MIN(arrival_date) as min_date,
               MAX(arrival_date) as max_date
        FROM market_prices
        WHERE {where}
        """,
        params,
    )
    
    count = row["cnt"] if row else 0
    min_date = row["min_date"] if row else None
    max_date = row["max_date"] if row else None
    
def check_data_availability(
    market: str,
    commodity: str,
    variety: Optional[str] = None,
) -> dict:
    """
    Check karta hai ki market+commodity+variety ka data available hai.
    
    PROTOTYPE MODE: 0 se zyada records hone chahiye, bas.
    (Original design me 30 records minimum tha, lekin prototype
    me data kam hai — isliye strict threshold hata diya.)
    
    Returns:
        dict: {
            "available": bool,
            "record_count": int,
            "date_range": {"min": ..., "max": ...},
            "warning": str or None
        }
    """
    where = "market = ? AND commodity = ?"
    params = [market, commodity]
    
    if variety:
        where += " AND variety = ?"
        params.append(variety)
    
    row = fetch_one(
        f"""
        SELECT COUNT(*) as cnt,
               MIN(arrival_date) as min_date,
               MAX(arrival_date) as max_date
        FROM market_prices
        WHERE {where}
        """,
        params,
    )
    
    count = row["cnt"] if row else 0
    min_date = row["min_date"] if row else None
    max_date = row["max_date"] if row else None
    
    # Warning logic (prototype ke liye simple)
    warning = None
    if count == 0:
        warning = f"Koi data nahi mila: {market} / {commodity}"
    elif count < MIN_RECORDS_WARNING:
        warning = (
            f"Sirf {count} records hain. Prediction kam accurate ho sakti hai "
            f"(accuracy ke liye {MIN_RECORDS_WARNING}+ records better hain)."
        )
    
    return {
        "available": count > 0,   # 0 ke alawa sab allowed (prototype)
        "record_count": count,
        "date_range": {"min": min_date, "max": max_date},
        "warning": warning,
    }


# ============================================================
# SECTION 3: INPUT VALIDATION
# ============================================================

def validate_input(
    state: str,
    district: str,
    market: str,
    commodity: str,
    variety: Optional[str],
    start_date: date,
    days: int,
    quantity_kg: Optional[float],
) -> None:
    """
    User input validation. Raises ValueError if invalid.
    """
    # Required fields
    if not state or not state.strip():
        raise ValueError("State required hai")
    if not market or not market.strip():
        raise ValueError("Market required hai")
    if not commodity or not commodity.strip():
        raise ValueError("Commodity required hai")
    
    # Date validation
    if not isinstance(start_date, date):
        raise ValueError("start_date date object hona chahiye")
    
    today = date.today()
    if start_date < today:
        raise ValueError("Past date ka prediction nahi ho sakta. Aaj ya future date chuno.")
    
    # Days validation
    if days < 1 or days > 30:
        raise ValueError("days 1-30 ke beech hona chahiye")
    
    # Quantity validation
    if quantity_kg is not None:
        if quantity_kg <= 0:
            raise ValueError("Quantity positive honi chahiye")


# ============================================================
# SECTION 4: EXPECTED VALUE CALCULATION
# ============================================================
# Ye SRS ka important design decision hai:
#   Quantity ML model ka input nahi hai.
#   Sirf prediction ke baad business calculation ke liye use hota hai.
# ============================================================

def _calculate_expected_value(
    modal_price_per_quintal: float,
    quantity_kg: Optional[float],
) -> Optional[dict]:
    """
    Expected gross value calculate karta hai (with unit conversion).
    
    Args:
        modal_price_per_quintal: Predicted modal price (₹/quintal)
        quantity_kg: User ki quantity (kg me)
    
    Returns:
        dict or None: {
            "quantity_kg": float,
            "quantity_quintal": float,
            "price_per_kg": float,
            "price_per_quintal": float,
            "expected_value": float
        }
    """
    if quantity_kg is None or quantity_kg <= 0:
        return None
    
    # Conversion
    price_per_kg = modal_price_per_quintal / QUINTAL_TO_KG
    quantity_quintal = quantity_kg / QUINTAL_TO_KG
    
    # Expected value = quantity_kg × price_per_kg
    # OR equivalent: quantity_quintal × price_per_quintal
    expected_value = quantity_kg * price_per_kg
    
    return {
        "quantity_kg": round(quantity_kg, 2),
        "quantity_quintal": round(quantity_quintal, 4),
        "price_per_kg": round(price_per_kg, 2),
        "price_per_quintal": round(modal_price_per_quintal, 2),
        "expected_value": round(expected_value, 2),
    }


# ============================================================
# SECTION 5: MAIN PREDICTION SERVICE
# ============================================================

def predict_price(
    state: str,
    district: str,
    market: str,
    commodity: str,
    variety: Optional[str] = None,
    start_date: Optional[date] = None,
    days: int = 10,
    quantity_kg: Optional[float] = None,
    log_prediction: bool = True,
) -> dict:
    """
    Full prediction pipeline.
    
    Args:
        state, district, market, commodity, variety: Filters
        start_date: Prediction date (default: kal)
        days: Forecast days (default: 10)
        quantity_kg: Optional quantity for expected value
        log_prediction: prediction_logs table me save karna hai?
    
    Returns:
        dict: {
            "selected_date": {...},
            "forecast": [...],
            "expected_value": {...} or None,
            "data_info": {"record_count": int, "warning": str},
            "model_info": {...},
            "generated_at": "..."
        }
    
    Raises:
        PredictionError: Agar prediction fail ho
        ValueError: Agar input invalid ho
    """
    # Default date = kal
    if start_date is None:
        start_date = date.today() + timedelta(days=1)
    
    # --------------------------------------------------------
    # STEP 1: Validate input
    # --------------------------------------------------------
    validate_input(
        state=state, district=district, market=market,
        commodity=commodity, variety=variety,
        start_date=start_date, days=days, quantity_kg=quantity_kg,
    )
    
    logger.info(
        f"Prediction request: {market}/{commodity}/{variety} "
        f"on {start_date} for {days} days"
    )
    
    # --------------------------------------------------------
    # STEP 2: Data availability check
    # --------------------------------------------------------
    availability = check_data_availability(market, commodity, variety)
    
    if not availability["available"]:
        raise PredictionError(
            availability["warning"] or "Data available nahi hai",
            details={
                "market": market,
                "commodity": commodity,
                "variety": variety,
                "record_count": availability["record_count"],
            },
        )
    
    if availability["warning"]:
        logger.warning(availability["warning"])
    
    # --------------------------------------------------------
    # STEP 3: Model load (fail early agar model nahi hai)
    # --------------------------------------------------------
    try:
        bundle = _load_model()
    except ModelNotFoundError as e:
        raise PredictionError(f"Model available nahi hai: {e}")
    
    # --------------------------------------------------------
    # STEP 4: Single date prediction (selected date)
    # --------------------------------------------------------
    try:
        selected = predict_for_date(
            state=state, district=district, market=market,
            commodity=commodity, variety=variety,
            target_date=start_date,
        )
    except Exception as e:
        logger.exception(f"Selected date prediction fail: {e}")
        raise PredictionError(f"Prediction fail hui: {e}")
    
    # --------------------------------------------------------
    # STEP 5: Next N days forecast
    # --------------------------------------------------------
    forecast = []
    try:
        next_start = start_date + timedelta(days=1)
        forecast = forecast_next_days(
            state=state, district=district, market=market,
            commodity=commodity, variety=variety,
            start_date=next_start,
            days=days,
        )
    except Exception as e:
        logger.exception(f"Forecast fail: {e}")
        # Forecast fail ho jaye to bhi single prediction return karo
        logger.warning("Forecast skip ho gaya, sirf selected date return kar rahe hain.")
    
    # --------------------------------------------------------
    # STEP 6: Expected value calculation
    # --------------------------------------------------------
    expected_value_info = _calculate_expected_value(
        modal_price_per_quintal=selected["modal_price"],
        quantity_kg=quantity_kg,
    )
    
    # --------------------------------------------------------
    # STEP 7: Build response
    # --------------------------------------------------------
    result = {
        "selected_date": selected,
        "forecast": forecast,
        "expected_value": expected_value_info,
        "data_info": {
            "record_count": availability["record_count"],
            "date_range": availability["date_range"],
            "warning": availability["warning"],
        },
        "model_info": {
            "name": bundle.get("model_name", "unknown"),
            "test_r2": round(bundle.get("test_r2_avg", 0), 4),
            "test_mape": round(bundle.get("test_mape", 0), 2),
            "version": "v1",
        },
        "input": {
            "state": state,
            "district": district,
            "market": market,
            "commodity": commodity,
            "variety": variety,
            "start_date": start_date.strftime("%Y-%m-%d"),
            "days": days,
            "quantity_kg": quantity_kg,
        },
        "generated_at": datetime.now().isoformat(timespec="seconds"),
    }
    
    # --------------------------------------------------------
    # STEP 8: Log prediction (optional)
    # --------------------------------------------------------
    if log_prediction:
        try:
            _log_prediction(result)
        except Exception as e:
            logger.warning(f"Prediction log fail: {e}")
    
    logger.info(
        f"✅ Prediction done: modal=₹{selected['modal_price']}, "
        f"forecast_days={len(forecast)}"
    )
    
    return result


# ============================================================
# SECTION 6: PREDICTION LOGGING
# ============================================================

def _log_prediction(result: dict) -> None:
    """
    prediction_logs table me entry save karta hai.
    Future me prediction vs actual comparison ke liye.
    """
    inp = result["input"]
    sel = result["selected_date"]
    
    execute_query(
        """
        INSERT INTO prediction_logs
            (state, district, market, commodity, variety, requested_date,
             predicted_price, model_version, quantity_kg, expected_value)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            inp["state"], inp["district"], inp["market"],
            inp["commodity"], inp["variety"], inp["start_date"],
            sel["modal_price"], result["model_info"]["version"],
            inp["quantity_kg"],
            result["expected_value"]["expected_value"] if result["expected_value"] else None,
        ),
    )
    logger.debug("Prediction logged successfully")


# ============================================================
# SECTION 7: HELPER — MARKET/COMMODITY INFO
# ============================================================

def get_available_markets(state: Optional[str] = None) -> list:
    """State ke markets (Dashboard ka cascading API already hai, but ML specific)."""
    if state:
        rows = fetch_all(
            "SELECT DISTINCT market FROM market_prices WHERE state = ? ORDER BY market",
            (state,),
        )
    else:
        rows = fetch_all("SELECT DISTINCT market FROM market_prices ORDER BY market")
    return [r["market"] for r in rows]


def get_market_data_summary(market: str, commodity: str, variety: Optional[str] = None) -> dict:
    """Ek specific market/commodity ka data summary."""
    return check_data_availability(market, commodity, variety)


# ============================================================
# SECTION 8: DIRECT RUN — Quick Test
# ============================================================
if __name__ == "__main__":
    print("=" * 65)
    print("KisanBazaar AI — ML Services Test")
    print("=" * 65)
    
    # Find a well-populated group
    sample = fetch_all("""
        SELECT state, district, market, commodity, variety, COUNT(*) as cnt
        FROM market_prices
        WHERE variety IS NOT NULL AND variety != ''
        GROUP BY state, district, market, commodity, variety
        ORDER BY cnt DESC
        LIMIT 1
    """)
    
    if not sample:
        print("❌ DB me data nahi hai.")
        sys.exit(1)
    
    s = sample[0]
    print(f"\nTest group: {s['market']} / {s['commodity']} / {s['variety']} ({s['cnt']} records)")
    
    # --------------------------------------------------------
    # Test 1: Data availability
    # --------------------------------------------------------
    print("\n--- Test 1: Data availability ---")
    avail = check_data_availability(s["market"], s["commodity"], s["variety"])
    for k, v in avail.items():
        print(f"  {k}: {v}")
    
    # --------------------------------------------------------
    # Test 2: Full prediction WITHOUT quantity
    # --------------------------------------------------------
    print("\n--- Test 2: Prediction (no quantity) ---")
    try:
        result = predict_price(
            state=s["state"], district=s["district"],
            market=s["market"], commodity=s["commodity"],
            variety=s["variety"],
            start_date=date.today() + timedelta(days=1),
            days=5,
            quantity_kg=None,
        )
        
        print(f"Selected: {result['selected_date']}")
        print(f"Forecast days: {len(result['forecast'])}")
        print(f"Expected value: {result['expected_value']} (should be None)")
        print(f"Model R²: {result['model_info']['test_r2']}")
        
    except Exception as e:
        print(f"❌ Prediction fail: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    
    # --------------------------------------------------------
    # Test 3: Full prediction WITH quantity (unit conversion test)
    # --------------------------------------------------------
    print("\n--- Test 3: Prediction (100 kg quantity) ---")
    try:
        result = predict_price(
            state=s["state"], district=s["district"],
            market=s["market"], commodity=s["commodity"],
            variety=s["variety"],
            start_date=date.today() + timedelta(days=1),
            days=5,
            quantity_kg=100,   # 100 kg
            log_prediction=False,   # Test me log nahi
        )
        
        sel = result["selected_date"]
        ev = result["expected_value"]
        
        print(f"Modal price: ₹{sel['modal_price']}/quintal")
        print(f"Price per kg: ₹{ev['price_per_kg']}")
        print(f"Quantity: {ev['quantity_kg']} kg = {ev['quantity_quintal']} quintal")
        print(f"Expected gross value: ₹{ev['expected_value']}")
        
        # Sanity check
        expected = sel["modal_price"] * (100 / 100)
        print(f"\nVerify: {sel['modal_price']} × 1 quintal = ₹{expected}")
        
    except Exception as e:
        print(f"❌ Quantity prediction fail: {e}")
        import traceback
        traceback.print_exc()
    
    # --------------------------------------------------------
    # Test 4: Input validation
    # --------------------------------------------------------
    print("\n--- Test 4: Input validation (bad inputs) ---")
    bad_cases = [
        ("Empty market", {"market": "", "start_date": date.today() + timedelta(days=1)}),
        ("Past date", {"market": s["market"], "start_date": date.today() - timedelta(days=1)}),
        ("Negative quantity", {"market": s["market"], "start_date": date.today() + timedelta(days=1), "quantity_kg": -50}),
    ]
    
    for name, overrides in bad_cases:
        args = {
            "state": s["state"], "district": s["district"],
            "market": s["market"], "commodity": s["commodity"],
            "variety": s["variety"],
            "start_date": date.today() + timedelta(days=1),
            "days": 5,
        }
        args.update(overrides)
        
        try:
            predict_price(**args, log_prediction=False)
            print(f"  ⚠️  {name}: Should have failed but didn't")
        except ValueError as e:
            print(f"  ✅ {name}: {e}")
        except Exception as e:
            print(f"  ⚠️  {name}: Different error: {e}")
    
    print("\n" + "=" * 65)
    print("✅ ML services test complete.")