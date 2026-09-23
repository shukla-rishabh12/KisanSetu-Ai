# ============================================================
# KisanBazaar AI — ML Feature Engineering
# ============================================================
# Ye file notebook (Untitled7.ipynb) ka EXACT port hai.
# Prediction ke waqt same 51 features banane hain jo training me the.
#
# IMPORTANT: Notebook ke features aur yahan ke features IDENTICAL hone chahiye.
# Kahin bhi shortcut nahi karenge, warna model galat predict karega.
#
# NOTEBOOK KE FEATURES (51 total):
#   Categorical (5):
#     State, District, Market, Commodity, Variety
#   Lags (14):
#     Modal_lag_1, 2, 3, 5, 7, 14, 21, 30, 60, 90
#     Min_lag_1, 3, 7, 14
#     Max_lag_1, 3, 7, 14
#   Rolling (10):
#     Modal_roll_mean_7, 14, 30
#     Modal_roll_std_7, 30
#     Modal_roll_min_7, 30
#     Modal_roll_max_7, 30
#   Trend/Volatility/Ratio (5):
#     Modal_trend_7, Modal_trend_30, Modal_volatility_7
#     Min_Max_ratio_lag1, Modal_Max_ratio_lag1
#   Seasonality (5):
#     sin_doy, cos_doy, sin_month, cos_month, is_weekend
#   Z-score (1):
#     Modal_zscore_30
#   Aggregates (2):
#     comm_mean_lag1, state_mean_lag1
#   Relative (2):
#     rel_to_comm, rel_to_state
#   Date features (3):
#     Month, DayOfWeek, DayOfYear
#
# ============================================================

import sys
import numpy as np
import pandas as pd
from pathlib import Path
from datetime import datetime, timedelta

# ------------------------------------------------------------
# PATH FIX
# ------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# Project imports
from core.logger import get_logger

# Logger
logger = get_logger(__name__)


# ============================================================
# CONSTANTS (notebook se exact match)
# ============================================================

GROUP_KEYS = ["State", "District", "Market", "Commodity", "Variety"]
PRICE_COLS = ["Min_Price", "Max_Price", "Modal_Price"]
CAT_FEATURES = ["State", "District", "Market", "Commodity", "Variety"]

# Lag windows (notebook Cell 5)
MODAL_LAGS = [1, 2, 3, 5, 7, 14, 21, 30, 60, 90]
MIN_LAGS = [1, 3, 7, 14]
MAX_LAGS = [1, 3, 7, 14]

# Rolling windows (notebook Cell 6)
ROLL_MEAN_WINDOWS = [7, 14, 30]
ROLL_STD_WINDOWS = [7, 14, 30]
ROLL_MIN_WINDOWS = [7, 30]
ROLL_MAX_WINDOWS = [7, 30]


# ============================================================
# SECTION 1: DATA CLEANING (notebook Cell 3 equivalent)
# ============================================================

def clean_prices(df: pd.DataFrame) -> pd.DataFrame:
    """
    Notebook ke Cell 3 ka cleaning logic.
    - Price columns numeric
    - Negative / zero → NaN
    - NaN → row median → global median
    
    Args:
        df: DataFrame with Min_Price, Max_Price, Modal_Price
        
    Returns:
        Cleaned DataFrame
    """
    df = df.copy()
    
    for c in PRICE_COLS:
        df[c] = pd.to_numeric(df[c], errors="coerce")
        df.loc[df[c] <= 0, c] = np.nan
    
    # Row median fill
    row_med = df[PRICE_COLS].median(axis=1, skipna=True)
    gmed = {c: df.loc[df[c] > 0, c].median() for c in PRICE_COLS}
    
    for c in PRICE_COLS:
        m = df[c].isna()
        df.loc[m, c] = row_med[m]
        s = df[c].isna()
        df.loc[s, c] = gmed[c]
        df[c] = df[c].astype("float32")
    
    # Min/Max swap
    mask = df["Min_Price"] > df["Max_Price"]
    if mask.any():
        df.loc[mask, ["Min_Price", "Max_Price"]] = \
            df.loc[mask, ["Max_Price", "Min_Price"]].values
    
    # Clip Modal
    df["Modal_Price"] = df["Modal_Price"].clip(
        df["Min_Price"], df["Max_Price"]
    ).astype("float32")
    
    return df


# ============================================================
# SECTION 2: DAILY AGGREGATION (notebook Cell 4 equivalent)
# ============================================================

def aggregate_daily(df: pd.DataFrame) -> pd.DataFrame:
    """
    Ek market+commodity+variety ke multiple records per date ko
    ek row me aggregate karta hai (mean).
    
    Notebook ke Cell 4 ka logic.
    
    Args:
        df: DataFrame with raw records (multiple per day)
        
    Returns:
        DataFrame with one row per date per group
    """
    # Ensure date is datetime
    if not pd.api.types.is_datetime64_any_dtype(df["date"]):
        df = df.copy()
        df["date"] = pd.to_datetime(df["date"])
    
    # Aggregate
    daily = (
        df.groupby(GROUP_KEYS + ["date"], observed=True)[PRICE_COLS]
        .mean()
        .reset_index()
        .sort_values(GROUP_KEYS + ["date"])
        .reset_index(drop=True)
    )
    
    for c in PRICE_COLS:
        daily[c] = daily[c].astype("float32")
    
    return daily


# ============================================================
# SECTION 3: TIME FEATURES
# ============================================================

def add_time_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Notebook Cell 3 ka time features part.
    Month, DayOfWeek, DayOfYear
    """
    df = df.copy()
    df["Month"] = df["date"].dt.month.astype("int8")
    df["DayOfWeek"] = df["date"].dt.dayofweek.astype("int8")
    df["DayOfYear"] = df["date"].dt.dayofyear.astype("int16")
    return df


# ============================================================
# SECTION 4: LAG FEATURES (notebook Cell 5 equivalent)
# ============================================================

def add_lag_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Notebook Cell 5: Lags on Modal, Min, Max.
    """
    df = df.copy()
    g = df.groupby(GROUP_KEYS, observed=True, sort=False)
    
    # Modal lags
    for lag in MODAL_LAGS:
        df[f"Modal_lag_{lag}"] = g["Modal_Price"].shift(lag).astype("float32")
    
    # Min lags
    for lag in MIN_LAGS:
        df[f"Min_lag_{lag}"] = g["Min_Price"].shift(lag).astype("float32")
    
    # Max lags
    for lag in MAX_LAGS:
        df[f"Max_lag_{lag}"] = g["Max_Price"].shift(lag).astype("float32")
    
    return df


# ============================================================
# SECTION 5: ROLLING FEATURES (notebook Cell 6 equivalent)
# ============================================================

def add_rolling_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Notebook Cell 6: Rolling stats on shifted Modal.
    
    NOTE: Rolling is computed on Modal_Price shifted by 1 (to avoid leakage).
    """
    df = df.copy()
    
    # Shift modal by 1 first (used for all rolling)
    df["_s1"] = df.groupby(GROUP_KEYS, observed=True)["Modal_Price"] \
                  .shift(1).astype("float32")
    
    def groll(col, w, method, mp=1):
        r = df.groupby(GROUP_KEYS, observed=True)[col] \
              .rolling(w, min_periods=mp).agg(method)
        r.index = r.index.droplevel(list(range(len(GROUP_KEYS))))
        return r.sort_index()
    
    # Mean and std
    for w in ROLL_MEAN_WINDOWS:
        df[f"Modal_roll_mean_{w}"] = groll("_s1", w, "mean", 1).astype("float32")
    for w in ROLL_STD_WINDOWS:
        df[f"Modal_roll_std_{w}"] = groll("_s1", w, "std", 2).astype("float32")
    for w in ROLL_MIN_WINDOWS:
        df[f"Modal_roll_min_{w}"] = groll("_s1", w, "min", 1).astype("float32")
    for w in ROLL_MAX_WINDOWS:
        df[f"Modal_roll_max_{w}"] = groll("_s1", w, "max", 1).astype("float32")
    
    # Trend
    df["Modal_trend_7"] = (df["Modal_lag_1"] - df["Modal_lag_7"]).astype("float32")
    df["Modal_trend_30"] = (df["Modal_lag_1"] - df["Modal_lag_30"]).astype("float32")
    
    # Volatility
    df["Modal_volatility_7"] = (
        df["Modal_roll_std_7"] / (df["Modal_roll_mean_7"] + 1)
    ).astype("float32")
    
    # Ratios
    df["Min_Max_ratio_lag1"] = (
        df["Min_lag_1"] / (df["Max_lag_1"] + 1)
    ).astype("float32")
    df["Modal_Max_ratio_lag1"] = (
        df["Modal_lag_1"] / (df["Max_lag_1"] + 1)
    ).astype("float32")
    
    df = df.drop(columns=["_s1"])
    return df


# ============================================================
# SECTION 6: SEASONALITY (notebook Cell 7 equivalent)
# ============================================================

def add_seasonality_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Notebook Cell 7: sin/cos of dayofyear and month, weekend flag, z-score.
    """
    df = df.copy()
    
    doy = df["date"].dt.dayofyear
    mon = df["date"].dt.month
    
    df["sin_doy"] = np.sin(2 * np.pi * doy / 365.25).astype("float32")
    df["cos_doy"] = np.cos(2 * np.pi * doy / 365.25).astype("float32")
    df["sin_month"] = np.sin(2 * np.pi * mon / 12).astype("float32")
    df["cos_month"] = np.cos(2 * np.pi * mon / 12).astype("float32")
    df["is_weekend"] = (df["DayOfWeek"] >= 5).astype("int8")
    
    # Z-score
    df["Modal_zscore_30"] = (
        (df["Modal_lag_1"] - df["Modal_roll_mean_30"]) /
        (df["Modal_roll_std_30"] + 1)
    ).astype("float32")
    
    return df


# ============================================================
# SECTION 7: AGGREGATE FEATURES (notebook Cell 7 equivalent)
# ============================================================
# These need data from OTHER markets / states. For prediction, we
# need to pass this data from the DB along with the target market's data.
# ============================================================

def compute_commodity_day_aggregates(commodity_df: pd.DataFrame) -> pd.DataFrame:
    """
    Same commodity, all markets ke daily mean and std.
    Returns DataFrame with columns: [Commodity, date, comm_mean, comm_std, comm_mean_lag1]
    """
    cd = (
        commodity_df.groupby(["Commodity", "date"], observed=True)["Modal_Price"]
        .agg(["mean", "std"])
        .reset_index()
    )
    cd.columns = ["Commodity", "date", "comm_mean", "comm_std"]
    cd = cd.sort_values(["Commodity", "date"])
    cd["comm_mean_lag1"] = (
        cd.groupby("Commodity")["comm_mean"].shift(1).astype("float32")
    )
    return cd[["Commodity", "date", "comm_mean_lag1"]]


def compute_state_day_aggregates(state_df: pd.DataFrame) -> pd.DataFrame:
    """
    Same state, all markets ke daily mean.
    Returns DataFrame with columns: [State, date, state_mean_lag1]
    """
    sd = (
        state_df.groupby(["State", "date"], observed=True)["Modal_Price"]
        .mean()
        .reset_index()
    )
    sd.columns = ["State", "date", "state_mean"]
    sd = sd.sort_values(["State", "date"])
    sd["state_mean_lag1"] = (
        sd.groupby("State")["state_mean"].shift(1).astype("float32")
    )
    return sd[["State", "date", "state_mean_lag1"]]


def add_aggregate_features(
    df: pd.DataFrame,
    comm_agg: pd.DataFrame,
    state_agg: pd.DataFrame,
) -> pd.DataFrame:
    """
    Notebook Cell 7: merge aggregates + compute relative features.
    """
    df = df.copy()
    
    # Merge commodity-day
    df = df.merge(comm_agg, on=["Commodity", "date"], how="left")
    
    # Merge state-day
    df = df.merge(state_agg, on=["State", "date"], how="left")
    
    # Relative
    df["rel_to_comm"] = (
        df["Modal_lag_1"] / (df["comm_mean_lag1"] + 1)
    ).astype("float32")
    df["rel_to_state"] = (
        df["Modal_lag_1"] / (df["state_mean_lag1"] + 1)
    ).astype("float32")
    
    return df


# ============================================================
# SECTION 8: MAIN ORCHESTRATOR
# ============================================================

def engineer_all_features(
    market_df: pd.DataFrame,
    comm_agg: pd.DataFrame,
    state_agg: pd.DataFrame,
) -> pd.DataFrame:
    """
    Poora feature engineering pipeline. Notebook ke Cell 3-7 ka equivalent.
    
    Args:
        market_df: Target market+commodity+variety ka daily data
                   (raw records — multiple per date possible)
        comm_agg: Commodity-day aggregates (from compute_commodity_day_aggregates)
        state_agg: State-day aggregates (from compute_state_day_aggregates)
    
    Returns:
        DataFrame with all 51 features
    """
    # Clean prices
    df = clean_prices(market_df)
    
    # Daily aggregate
    daily = aggregate_daily(df)
    
    # Add time features
    daily = add_time_features(daily)
    
    # Add lags
    daily = add_lag_features(daily)
    
    # Add rolling
    daily = add_rolling_features(daily)
    
    # Add seasonality
    daily = add_seasonality_features(daily)
    
    # Add aggregates
    daily = add_aggregate_features(daily, comm_agg, state_agg)
    
    # Force float32 on all float64 columns
    for c in daily.columns:
        if daily[c].dtype == "float64":
            daily[c] = daily[c].astype("float32")
    
    return daily


# ============================================================
# SECTION 9: PREDICTION ROW BUILDER
# ============================================================
# Prediction ke waqt hum target date ke liye features banate hain,
# uske baad model se predict karte hain.
#
# Approach: 
#   1. Take historical daily data (up to today)
#   2. Append a placeholder row for target date (with NaN target)
#   3. Run feature engineering on whole thing
#   4. Take last row's features → model input
# ============================================================

def build_prediction_features(
    historical_daily: pd.DataFrame,
    target_date: pd.Timestamp,
    market: str,
    commodity: str,
    variety: str,
    state: str,
    district: str,
    comm_agg: pd.DataFrame,
    state_agg: pd.DataFrame,
) -> pd.DataFrame:
    """
    Ek single prediction date ke liye feature row build karta hai.
    
    Args:
        historical_daily: Daily aggregated data (State, District, Market,
                          Commodity, Variety, date, Min_Price, Max_Price, Modal_Price)
        target_date: Kis date ka prediction karna hai
        market, commodity, variety, state, district: Context
        comm_agg: Commodity-day aggregates (full, historical + target date placeholder)
        state_agg: State-day aggregates (full)
    
    Returns:
        pd.DataFrame with single row containing all features (ready for model)
    """
    # Append placeholder row for target date (target values = NaN)
    placeholder = pd.DataFrame([{
        "State": state,
        "District": district,
        "Market": market,
        "Commodity": commodity,
        "Variety": variety,
        "date": target_date,
        "Min_Price": np.nan,
        "Max_Price": np.nan,
        "Modal_Price": np.nan,
    }])
    
    combined = pd.concat([historical_daily, placeholder], ignore_index=True)
    combined = combined.sort_values("date").reset_index(drop=True)
    
    # Clean prices (only history has real values)
    # For placeholder, clean_prices will try to fill NaN — but we don't want that
    # So we skip clean_prices on the placeholder. Instead, we just ensure
    # history is already cleaned and placeholder stays NaN.
    
    # Add time features
    combined = add_time_features(combined)
    
    # Add lags (this will use history for the placeholder row)
    combined = add_lag_features(combined)
    
    # Add rolling
    combined = add_rolling_features(combined)
    
    # Add seasonality
    combined = add_seasonality_features(combined)
    
    # Add aggregates
    combined = add_aggregate_features(combined, comm_agg, state_agg)
    
    # Force float32
    for c in combined.columns:
        if combined[c].dtype == "float64":
            combined[c] = combined[c].astype("float32")
    
    # Return only the last row (placeholder)
    return combined.iloc[[-1]].reset_index(drop=True)


# ============================================================
# SECTION 10: 10-DAY FORECAST BUILDER
# ============================================================
# Recursive forecasting: predict day-by-day, feed predictions back as lags.
# ============================================================

def build_forecast_rows(
    historical_daily: pd.DataFrame,
    start_date: pd.Timestamp,
    days: int,
    market: str,
    commodity: str,
    variety: str,
    state: str,
    district: str,
    comm_agg: pd.DataFrame,
    state_agg: pd.DataFrame,
) -> pd.DataFrame:
    """
    N days ke liye feature rows build karta hai.
    
    Recursive approach:
      - Day 1: use history, predict
      - Day 2: append Day 1 prediction as new history, predict
      - ...
    
    Args:
        Same as build_prediction_features
        start_date: Pehli prediction date
        days: Kitne din (typically 10)
    
    Returns:
        DataFrame with `days` rows (one per date), each with all features
        NOTE: Target columns (Min/Max/Modal) will be NaN — model will fill
              them during prediction.
    """
    # Combined daily + placeholder rows for each forecast day
    placeholders = []
    for i in range(days):
        d = start_date + pd.Timedelta(days=i)
        placeholders.append({
            "State": state,
            "District": district,
            "Market": market,
            "Commodity": commodity,
            "Variety": variety,
            "date": d,
            "Min_Price": np.nan,
            "Max_Price": np.nan,
            "Modal_Price": np.nan,
        })
    
    combined = pd.concat(
        [historical_daily, pd.DataFrame(placeholders)],
        ignore_index=True,
    ).sort_values("date").reset_index(drop=True)
    
    # Time features
    combined = add_time_features(combined)
    
    # Lags — will use history; placeholder rows will have NaN for their own lags
    combined = add_lag_features(combined)
    
    # Rolling
    combined = add_rolling_features(combined)
    
    # Seasonality
    combined = add_seasonality_features(combined)
    
    # Aggregates
    combined = add_aggregate_features(combined, comm_agg, state_agg)
    
    # Force float32
    for c in combined.columns:
        if combined[c].dtype == "float64":
            combined[c] = combined[c].astype("float32")
    
    # Return only placeholder rows
    return combined.iloc[-days:].reset_index(drop=True)


# ============================================================
# SECTION 11: DIRECT RUN — Quick Test
# ============================================================
if __name__ == "__main__":
    print("=" * 65)
    print("KisanBazaar AI — Feature Engineering Test")
    print("=" * 65)
    
    # Sanity check: notebook ke features match ho rahe hain?
    # (Ye test DB ke data ke bina bhi chalega)
    
    print("\n--- Constants Check ---")
    print(f"Group keys       : {GROUP_KEYS}")
    print(f"Cat features     : {CAT_FEATURES}")
    print(f"Modal lags       : {MODAL_LAGS}")
    print(f"Min lags         : {MIN_LAGS}")
    print(f"Max lags         : {MAX_LAGS}")
    print(f"Rolling windows  : {ROLL_MEAN_WINDOWS + ROLL_STD_WINDOWS}")
    
    # Count expected features
    expected_lags = len(MODAL_LAGS) + len(MIN_LAGS) + len(MAX_LAGS)
    expected_rolling = (
        len(ROLL_MEAN_WINDOWS) + len(ROLL_STD_WINDOWS) +
        len(ROLL_MIN_WINDOWS) + len(ROLL_MAX_WINDOWS)
    )
    expected_other = 5 + 5 + 1 + 2 + 2 + 3  # seasonality+zscore+agg+rel+date
    expected_cats = 5
    
    print(f"\n--- Expected Feature Count ---")
    print(f"Categorical      : {expected_cats}")
    print(f"Lags             : {expected_lags}")
    print(f"Rolling          : {expected_rolling}")
    print(f"Trend/Vol/Ratio  : 5")
    print(f"Seasonality      : 5")
    print(f"Z-score          : 1")
    print(f"Aggregates       : 2")
    print(f"Relative         : 2")
    print(f"Date features    : 3")
    print(f"TOTAL            : {expected_cats + expected_lags + expected_rolling + 5 + 5 + 1 + 2 + 2 + 3}")
    
    print("\n(Notebook me 51 features the. Ye count 51 match karna chahiye.)")
    
    print("\n✅ Feature engineering module ready for testing with real DB data.")
    print("   Next: predict.py me model load + prediction logic.")