# ============================================================
# KisanBazaar AI — ML Predictor
# ============================================================
# Ye file model load + prediction logic rakhti hai.
#
# KAAM:
#   1. current_model.pkl load karna (lazy init)
#   2. DB se historical data laana (target group + aggregates)
#   3. Feature engineering call karna
#   4. Single date prediction
#   5. 10-day recursive forecast (day-by-day)
#   6. Log → real price conversion (expm1)
#
# IMPORTANT:
#   - Model "is_log=True" ke saath train hua hai — matlab targets
#     log1p me hain. Prediction ke baad expm1 karna zaroori hai.
#   - Recursive forecast me: Day N ki prediction Day N+1 ke lag me
#     feed hoti hai (kyunki actual price unknown hai).
#   - Target: Min_Price, Max_Price, Modal_Price — teeno predict hote hain.
# ============================================================

import sys
import numpy as np
import pandas as pd
import joblib
from pathlib import Path
from datetime import date, datetime, timedelta
from typing import Optional

# ------------------------------------------------------------
# PATH FIX
# ------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# Project imports
from config import MLConfig
from database.db import fetch_all
from core.logger import get_logger
from core.exceptions import ModelNotFoundError, PredictionError

from ml.feature_engineering import (
    GROUP_KEYS,
    PRICE_COLS,
    CAT_FEATURES,
    engineer_all_features,
    build_forecast_rows,
    add_time_features,
    add_lag_features,
    add_rolling_features,
    add_seasonality_features,
    add_aggregate_features,
    compute_commodity_day_aggregates,
    compute_state_day_aggregates,
    clean_prices,
    aggregate_daily,
)

# Logger
logger = get_logger(__name__)


# ============================================================
# SECTION 1: MODEL LOADING (lazy init)
# ============================================================
# Model 42MB ka hai. Har prediction pe load karna wasteful hai.
# Ek baar load karke memory me rakh lete hain (singleton).
# ============================================================

_model_bundle = None


def _load_model():
    """
    Model bundle load karta hai (lazy, singleton).
    
    Returns:
        dict: {
            "model": CatBoostRegressor,
            "feature_cols": list,
            "cat_features": list,
            "target_cols": list,
            "is_log": bool,
            ...
        }
    
    Raises:
        ModelNotFoundError: Agar model file nahi mili.
    """
    global _model_bundle
    
    if _model_bundle is not None:
        return _model_bundle
    
    model_path = MLConfig.CURRENT_MODEL_PATH
    
    if not model_path.exists():
        raise ModelNotFoundError(
            f"Model file nahi mili: {model_path}",
            details={"path": str(model_path)},
        )
    
    try:
        logger.info(f"Loading model from {model_path}...")
        _model_bundle = joblib.load(str(model_path))
        logger.info(
            f"✅ Model loaded: {_model_bundle.get('model_name', 'unknown')}, "
            f"{len(_model_bundle['feature_cols'])} features, "
            f"R²={_model_bundle.get('test_r2_avg', 'N/A')}"
        )
        return _model_bundle
    except Exception as e:
        raise ModelNotFoundError(
            f"Model load fail hua: {e}",
            details={"path": str(model_path), "error": str(e)},
        )


def reload_model():
    """Force reload (testing / retraining ke baad)."""
    global _model_bundle
    _model_bundle = None
    return _load_model()


# ============================================================
# SECTION 2: DB DATA FETCHING
# ============================================================

def _fetch_market_history(
    state: str,
    district: str,
    market: str,
    commodity: str,
    variety: Optional[str],
) -> pd.DataFrame:
    """
    Target market+commodity+variety ka historical daily data laata hai.
    
    Returns:
        DataFrame with columns:
        [State, District, Market, Commodity, Variety, date, Min_Price, Max_Price, Modal_Price]
    """
    # Build query
    where = "market = ? AND commodity = ?"
    params = [market, commodity]
    
    if variety:
        where += " AND variety = ?"
        params.append(variety)
    else:
        # If no variety specified, filter only rows with empty/null variety
        where += " AND (variety IS NULL OR variety = '')"
    
    query = f"""
        SELECT state, district, market, commodity, variety,
               arrival_date AS date,
               min_price AS Min_Price,
               max_price AS Max_Price,
               modal_price AS Modal_Price
        FROM market_prices
        WHERE {where}
        ORDER BY arrival_date ASC
    """
    
    rows = fetch_all(query, params)
    
    if not rows:
        return pd.DataFrame()
    
    df = pd.DataFrame(rows)
    
    # Rename capital-case columns to match notebook convention
    df = df.rename(columns={
        "state": "State",
        "district": "District",
        "market": "Market",
        "commodity": "Commodity",
        "variety": "Variety",
    })
    
    df["date"] = pd.to_datetime(df["date"])
    
    # Fill missing variety with empty string (consistency)
    df["Variety"] = df["Variety"].fillna("")
    
    return df










def _fetch_commodity_history(commodity: str, state: str = None) -> pd.DataFrame:
    """
    Same commodity ka data (aggregates ke liye).
    
    NOTE: state given ho to sirf usi state tak limit karo —
    query 10x-100x faster hoti hai. Prototype ke liye enough hai.
    """
    if state:
        query = """
            SELECT state, district, market, commodity, variety,
                   arrival_date AS date,
                   modal_price AS Modal_Price
            FROM market_prices
            WHERE commodity = ? AND state = ?
            ORDER BY arrival_date ASC
        """
        rows = fetch_all(query, (commodity, state))
    else:
        query = """
            SELECT state, district, market, commodity, variety,
                   arrival_date AS date,
                   modal_price AS Modal_Price
            FROM market_prices
            WHERE commodity = ?
            ORDER BY arrival_date ASC
        """
        rows = fetch_all(query, (commodity,))






    if not rows:
        return pd.DataFrame()
    
    df = pd.DataFrame(rows)
    df = df.rename(columns={
        "state": "State", "district": "District", "market": "Market",
        "commodity": "Commodity", "variety": "Variety",
    })
    df["date"] = pd.to_datetime(df["date"])
    return df


def _fetch_state_history(state: str) -> pd.DataFrame:
    """
    Same state, ALL markets ka data (state aggregates ke liye).
    """
    query = """
        SELECT state, district, market, commodity, variety,
               arrival_date AS date,
               modal_price AS Modal_Price
        FROM market_prices
        WHERE state = ?
        ORDER BY arrival_date ASC
    """
    rows = fetch_all(query, (state,))
    
    if not rows:
        return pd.DataFrame()
    
    df = pd.DataFrame(rows)
    df = df.rename(columns={
        "state": "State", "district": "District", "market": "Market",
        "commodity": "Commodity", "variety": "Variety",
    })
    df["date"] = pd.to_datetime(df["date"])
    return df


# ============================================================
# SECTION 3: MODEL PREDICTION HELPER
# ============================================================

def _predict_raw(feature_row: pd.DataFrame) -> np.ndarray:
    """
    Ek feature row pe model predict karta hai aur real prices return karta hai.
    
    Args:
        feature_row: Single row DataFrame with all features
    
    Returns:
        np.ndarray: [Min_Price, Max_Price, Modal_Price] in real (non-log) scale
    """
    bundle = _load_model()
    model = bundle["model"]
    feature_cols = bundle["feature_cols"]
    cat_features = bundle["cat_features"]
    target_cols = bundle["target_cols"]
    is_log = bundle.get("is_log", True)
    
    # Ensure feature order matches training
    X = feature_row[feature_cols].copy()
    
    # Ensure categorical columns are strings (CatBoost native support)
    for c in cat_features:
        X[c] = X[c].astype(str)
    
    # Predict
    try:
        pred = model.predict(X)
    except Exception as e:
        raise PredictionError(
            f"Model predict fail: {e}",
            details={"features_count": len(feature_cols)},
        )
    
    # Ensure 2D
    if pred.ndim == 1:
        pred = pred.reshape(-1, 3)
    
    # Inverse log transform
    if is_log:
        pred = np.expm1(pred)
    
    # Clip negatives to 0
    pred = np.maximum(pred, 0)
    
    return pred


# ============================================================
# SECTION 4: SINGLE DATE PREDICTION
# ============================================================

def predict_for_date(
    state: str,
    district: str,
    market: str,
    commodity: str,
    variety: Optional[str],
    target_date: date,
) -> dict:
    """
    Ek specific date ka price predict karta hai.
    
    Args:
        state, district, market, commodity, variety: Filter context
        target_date: Kis date ka prediction (future date)
    
    Returns:
        dict: {
            "date": "YYYY-MM-DD",
            "min_price": float,
            "max_price": float,
            "modal_price": float,
        }
    """
    logger.info(
        f"Predicting for {market}/{commodity}/{variety} on {target_date}"
    )
    
    # --------------------------------------------------------
    # Fetch historical data (target + aggregates)
    # --------------------------------------------------------
    market_df = _fetch_market_history(state, district, market, commodity, variety)
    
    if market_df.empty:
        raise PredictionError(
            f"Historical data nahi mila: {market}/{commodity}/{variety}",
            details={"market": market, "commodity": commodity},
        )
    
    if len(market_df) < 30:
        logger.warning(
            f"Sirf {len(market_df)} records hain. Prediction kam accurate ho sakti hai."
        )

    








    # Aggregates
    comm_df = _fetch_commodity_history(commodity, state=state)











    state_df = _fetch_state_history(state)
    
    if comm_df.empty or state_df.empty:
        raise PredictionError("Aggregate data missing for commodity/state")
    
    # Compute aggregates
    comm_agg = compute_commodity_day_aggregates(comm_df)
    state_agg = compute_state_day_aggregates(state_df)
    
    # --------------------------------------------------------
    # Prepare historical daily (clean + aggregate)
    # --------------------------------------------------------
    market_clean = clean_prices(market_df)
    market_daily = aggregate_daily(market_clean)
    
    # --------------------------------------------------------
    # Build feature row for target date
    # --------------------------------------------------------
    target_ts = pd.Timestamp(target_date)
    
    # Append placeholder row
    placeholder = pd.DataFrame([{
        "State": state,
        "District": district,
        "Market": market,
        "Commodity": commodity,
        "Variety": variety or "",
        "date": target_ts,
        "Min_Price": np.nan,
        "Max_Price": np.nan,
        "Modal_Price": np.nan,
    }])
    
    combined = pd.concat([market_daily, placeholder], ignore_index=True)
    combined = combined.sort_values("date").reset_index(drop=True)
    
    # Feature engineering
    combined = add_time_features(combined)
    combined = add_lag_features(combined)
    combined = add_rolling_features(combined)
    combined = add_seasonality_features(combined)
    combined = add_aggregate_features(combined, comm_agg, state_agg)
    
    # Force float32
    for c in combined.columns:
        if combined[c].dtype == "float64":
            combined[c] = combined[c].astype("float32")
    
    # Last row = placeholder
    feature_row = combined.iloc[[-1]].reset_index(drop=True)
    
    # --------------------------------------------------------
    # Predict
    # --------------------------------------------------------
    pred = _predict_raw(feature_row)
    min_p, max_p, modal_p = pred[0]
    
    # Sanity: min <= modal <= max
    min_p, max_p = min(min_p, max_p), max(min_p, max_p)
    modal_p = np.clip(modal_p, min_p, max_p)
    
    result = {
        "date": target_date.strftime("%Y-%m-%d"),
        "min_price": round(float(min_p), 2),
        "max_price": round(float(max_p), 2),
        "modal_price": round(float(modal_p), 2),
    }
    
    logger.info(f"Prediction: {result}")
    return result


# ============================================================
# SECTION 5: 10-DAY RECURSIVE FORECAST
# ============================================================

def forecast_next_days(
    state: str,
    district: str,
    market: str,
    commodity: str,
    variety: Optional[str],
    start_date: date,
    days: int = 10,
) -> list[dict]:
    """
    Recursive multi-day forecast.
    
    Approach:
      1. Historical daily data lo
      2. Day 1 ke liye feature banao (history se lags)
      3. Predict
      4. Predicted values ko "as if actual" history me append karo
      5. Day 2 ke liye feature banao (ab history me Day 1 bhi hai)
      6. ...
      7. Days tak repeat
    
    Ye SRS me bola gaya "recursive forecasting" hai.
    
    Args:
        Same as predict_for_date
        start_date: Pehli date (usually kal se shuru)
        days: Kitne din (default 10)
    
    Returns:
        list[dict]: [
            {"date": "YYYY-MM-DD", "min_price": ..., "max_price": ..., "modal_price": ...},
            ...
        ]
    """
    logger.info(
        f"Forecasting {days} days for {market}/{commodity}/{variety} "
        f"starting {start_date}"
    )
    
    # --------------------------------------------------------
    # Fetch history
    # --------------------------------------------------------
    market_df = _fetch_market_history(state, district, market, commodity, variety)
    
    if market_df.empty:
        raise PredictionError(f"Historical data nahi mila for {market}/{commodity}")
    
    if len(market_df) < 60:
        logger.warning(
            f"Sirf {len(market_df)} records hain. Forecast accuracy kam ho sakti hai."
        )
    
    # Aggregates (fetch once, reuse across days)




















    comm_df = _fetch_commodity_history(commodity, state=state)















    
    state_df = _fetch_state_history(state)
    comm_agg = compute_commodity_day_aggregates(comm_df)
    state_agg = compute_state_day_aggregates(state_df)
    
    # Clean + aggregate history
    market_clean = clean_prices(market_df)
    market_daily = aggregate_daily(market_clean)
    
    # --------------------------------------------------------
    # Loop: predict one day at a time, feed back as history
    # --------------------------------------------------------
    results = []
    current_history = market_daily.copy()
    bundle = _load_model()
    feature_cols = bundle["feature_cols"]
    cat_features = bundle["cat_features"]
    is_log = bundle.get("is_log", True)
    
    for i in range(days):
        target_ts = pd.Timestamp(start_date) + pd.Timedelta(days=i)
        
        # Add placeholder for this date
        placeholder = pd.DataFrame([{
            "State": state,
            "District": district,
            "Market": market,
            "Commodity": commodity,
            "Variety": variety or "",
            "date": target_ts,
            "Min_Price": np.nan,
            "Max_Price": np.nan,
            "Modal_Price": np.nan,
        }])
        
        combined = pd.concat([current_history, placeholder], ignore_index=True)
        combined = combined.sort_values("date").reset_index(drop=True)
        
        # Feature engineering
        combined = add_time_features(combined)
        combined = add_lag_features(combined)
        combined = add_rolling_features(combined)
        combined = add_seasonality_features(combined)
        combined = add_aggregate_features(combined, comm_agg, state_agg)
        
        # Force float32
        for c in combined.columns:
            if combined[c].dtype == "float64":
                combined[c] = combined[c].astype("float32")
        
        # Get last row (placeholder) as feature row
        feature_row = combined.iloc[[-1]].reset_index(drop=True)
        
        # Predict
        pred = _predict_raw(feature_row)
        min_p, max_p, modal_p = pred[0]
        
        # Sanity
        min_p, max_p = min(min_p, max_p), max(min_p, max_p)
        modal_p = np.clip(modal_p, min_p, max_p)
        
        result = {
            "date": target_ts.strftime("%Y-%m-%d"),
            "min_price": round(float(min_p), 2),
            "max_price": round(float(max_p), 2),
            "modal_price": round(float(modal_p), 2),
        }
        results.append(result)
        
        # Append prediction as new "history" row for next iteration
        new_row = pd.DataFrame([{
            "State": state,
            "District": district,
            "Market": market,
            "Commodity": commodity,
            "Variety": variety or "",
            "date": target_ts,
            "Min_Price": float(min_p),
            "Max_Price": float(max_p),
            "Modal_Price": float(modal_p),
        }])
        current_history = pd.concat(
            [current_history, new_row], ignore_index=True
        )
    
    logger.info(f"✅ Forecast complete: {len(results)} days")
    return results


# ============================================================
# SECTION 6: FULL PREDICTION SERVICE
# ============================================================

def predict_full(
    state: str,
    district: str,
    market: str,
    commodity: str,
    variety: Optional[str],
    start_date: date,
    days: int = 10,
    quantity_kg: Optional[float] = None,
) -> dict:
    """
    Complete prediction: selected date + next N days + expected gross value.
    
    Args:
        state, district, market, commodity, variety: Filter
        start_date: Selected date (first prediction date)
        days: Kitne din ka forecast (default 10)
        quantity_kg: Optional — user ki quantity (expected value ke liye)
    
    Returns:
        dict: {
            "selected_date": {...},
            "forecast": [{...}, {...}, ...],
            "expected_gross_value": float or None,
            "quantity_kg": float or None,
            "model_info": {...}
        }
    """
    bundle = _load_model()
    
    # --------------------------------------------------------
    # Selected date prediction (Day 0)
    # --------------------------------------------------------
    selected = predict_for_date(
        state=state, district=district, market=market,
        commodity=commodity, variety=variety,
        target_date=start_date,
    )
    
    # --------------------------------------------------------
    # Next N days forecast (start_date + 1 se start)
    # --------------------------------------------------------
    next_start = start_date + timedelta(days=1)
    forecast = forecast_next_days(
        state=state, district=district, market=market,
        commodity=commodity, variety=variety,
        start_date=next_start, days=days,
    )
    
    # --------------------------------------------------------
    # Expected gross value (agar quantity di gayi)
    # --------------------------------------------------------
    expected_value = None
    if quantity_kg and quantity_kg > 0:
        # Use selected date ka modal price
        expected_value = round(selected["modal_price"] * quantity_kg, 2)
    
    return {
        "selected_date": selected,
        "forecast": forecast,
        "quantity_kg": quantity_kg,
        "expected_gross_value": expected_value,
        "model_info": {
            "name": bundle.get("model_name", "unknown"),
            "test_r2": bundle.get("test_r2_avg"),
            "test_mape": bundle.get("test_mape"),
            "version": "v1",  # static for now
        },
    }


# ============================================================
# SECTION 7: DIRECT RUN — Quick Test
# ============================================================
if __name__ == "__main__":
    print("=" * 65)
    print("KisanBazaar AI — Predictor Test")
    print("=" * 65)
    
    # 1. Model load test
    print("\n--- Model Load Test ---")
    try:
        bundle = _load_model()
        print(f"✅ Model loaded: {bundle.get('model_name')}")
        print(f"   Features: {len(bundle['feature_cols'])}")
        print(f"   Test R²: {bundle.get('test_r2_avg'):.4f}")
        print(f"   Test MAPE: {bundle.get('test_mape'):.2f}%")
    except Exception as e:
        print(f"❌ Model load fail: {e}")
        sys.exit(1)
    
    # 2. Find a real market+commodity from DB
    print("\n--- Finding real data from DB ---")
    sample = fetch_all("""
        SELECT state, district, market, commodity, variety,
               COUNT(*) as cnt
        FROM market_prices
        WHERE variety IS NOT NULL AND variety != ''
        GROUP BY state, district, market, commodity, variety
        ORDER BY cnt DESC
        LIMIT 1
    """)
    
    if not sample:
        print("❌ DB me koi data nahi hai. Pehle bootstrap chalao.")
        sys.exit(1)
    
    s = sample[0]
    print(f"Test group: {s['market']} / {s['commodity']} / {s['variety']} ({s['cnt']} records)")
    
    # 3. Single date prediction test
    print("\n--- Single Date Prediction ---")
    try:
        target = date.today() + timedelta(days=1)
        pred = predict_for_date(
            state=s["state"],
            district=s["district"],
            market=s["market"],
            commodity=s["commodity"],
            variety=s["variety"],
            target_date=target,
        )
        print(f"✅ Prediction for {pred['date']}:")
        print(f"   Min:   ₹{pred['min_price']}")
        print(f"   Max:   ₹{pred['max_price']}")
        print(f"   Modal: ₹{pred['modal_price']}")
    except Exception as e:
        print(f"❌ Single prediction fail: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    
    # 4. Full prediction (10-day forecast)
    print("\n--- 10-Day Forecast ---")
    try:
        result = predict_full(
            state=s["state"],
            district=s["district"],
            market=s["market"],
            commodity=s["commodity"],
            variety=s["variety"],
            start_date=date.today() + timedelta(days=1),
            days=5,   # Test me 5 din (10 me time lagega)
            quantity_kg=100,
        )
        
        print(f"\nSelected: {result['selected_date']}")
        print(f"\nForecast:")
        for f in result["forecast"]:
            print(f"  {f['date']}: Modal ₹{f['modal_price']} "
                  f"(Min ₹{f['min_price']}, Max ₹{f['max_price']})")
        
        print(f"\nExpected gross value (100 kg): ₹{result['expected_gross_value']}")
        print(f"\nModel: {result['model_info']}")
    
    except Exception as e:
        print(f"❌ Forecast fail: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "=" * 65)
    print("✅ Predictor test complete.")