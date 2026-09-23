# ============================================================
# KisanBazaar AI — Dashboard Services (Business Logic)
# ============================================================
# Ye file Dashboard ki saari SQLite queries aur aggregation
# logic rakhti hai. Flask routes yahan se data lete hain.
#
# SEPARATION OF CONCERNS:
#   services.py → SQL queries, aggregation, calculations
#   routes.py   → HTTP handling, JSON response
#
# Isse debugging easy: agar data galat, to yahan dekho.
# Agar response format galat, to routes.py dekho.
#
# IMPORTANT (SRS):
#   - Dashboard CURRENT + HISTORICAL actual government data dikhata hai.
#   - Ye "kya hua" ka jawab deta hai, "kya hoga" ka nahi (wo ML ka kaam).
#   - Sirf SQLite se padhta hai. Koi ML/prediction isme nahi.
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
from database.db import fetch_all, fetch_one, count_rows
from core.logger import get_logger

# Logger
logger = get_logger(__name__)


# ============================================================
# SECTION 1: FILTER OPTIONS
# ============================================================
# Dashboard ke dropdowns ke liye distinct values.
# User jab filter select karta hai, tab ye list chahiye hoti hai.
# ============================================================

def get_filter_options() -> dict:
    """
    Dashboard ke saare filter dropdowns ke liye values return karta hai.

    Cascading filters:
      State → District → Market → Commodity → Variety

    Returns:
        dict: {
            "states": [...],
            "districts": [...],        # All districts (filter by state frontend pe)
            "markets": [...],
            "commodities": [...],
            "varieties": [...],
            "date_range": {"min": "YYYY-MM-DD", "max": "YYYY-MM-DD"}
        }

    NOTE: Hum har filter ke liye ALL distinct values dete hain.
    Frontend pe user state select kare to districts filter ho jayein.
    Backend pe sirf simple distinct values nikalna fast hai.
    """
    logger.debug("Fetching filter options...")

    # Helper: distinct values nikaalo (sorted)
    def distinct_values(column: str) -> list[str]:
        rows = fetch_all(
            f"SELECT DISTINCT {column} FROM market_prices "
            f"WHERE {column} IS NOT NULL AND {column} != '' "
            f"ORDER BY {column}"
        )
        return [row[column] for row in rows]

    # Saare filters ke liye distinct values
    states = distinct_values("state")
    districts = distinct_values("district")
    markets = distinct_values("market")
    commodities = distinct_values("commodity")
    varieties = distinct_values("variety")

    # Date range
    date_row = fetch_one(
        "SELECT MIN(arrival_date) as min_date, MAX(arrival_date) as max_date "
        "FROM market_prices"
    )

    return {
        "states": states,
        "districts": districts,
        "markets": markets,
        "commodities": commodities,
        "varieties": varieties,
        "date_range": {
            "min": date_row["min_date"] if date_row else None,
            "max": date_row["max_date"] if date_row else None,
        },
    }


# ============================================================
# SECTION 2: BUILD WHERE CLAUSE (Shared Helper)
# ============================================================
# Har query me same filters apply hote hain. Ye helper WHERE
# clause aur params build karta hai — code duplication avoid.
# ============================================================

def _build_where_clause(
    state: Optional[str] = None,
    district: Optional[str] = None,
    market: Optional[str] = None,
    commodity: Optional[str] = None,
    variety: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> tuple[str, list]:
    """
    Filters ke basis pe WHERE clause aur params build karta hai.

    Returns:
        tuple: (where_sql, params_list)

    Example:
        where, params = _build_where_clause(
            market="Kanpur",
            commodity="Potato",
            start_date="2025-09-19",
        )
        # where = "WHERE market = ? AND commodity = ? AND arrival_date >= ?"
        # params = ["Kanpur", "Potato", "2025-09-19"]
    """
    conditions = []
    params = []

    if state:
        conditions.append("state = ?")
        params.append(state)
    if district:
        conditions.append("district = ?")
        params.append(district)
    if market:
        conditions.append("market = ?")
        params.append(market)
    if commodity:
        conditions.append("commodity = ?")
        params.append(commodity)
    if variety:
        conditions.append("variety = ?")
        params.append(variety)
    if start_date:
        conditions.append("arrival_date >= ?")
        params.append(start_date)
    if end_date:
        conditions.append("arrival_date <= ?")
        params.append(end_date)

    if conditions:
        where_sql = "WHERE " + " AND ".join(conditions)
    else:
        where_sql = ""

    return where_sql, params


# ============================================================
# SECTION 3: LATEST PRICES (Dashboard Cards)
# ============================================================
# Dashboard ke top pe 4 cards hote hain:
#   Current Modal Price | Min | Max | Average
# Ye latest available date ka data dikhate hain.
# ============================================================

def get_latest_prices(
    market: str,
    commodity: str,
    variety: Optional[str] = None,
) -> Optional[dict]:
    """
    Latest available date ka price data return karta hai (cards ke liye).

    Args:
        market: Mandi name.
        commodity: Commodity name.
        variety: Variety (optional).

    Returns:
        dict ya None: {
            "arrival_date": "YYYY-MM-DD",
            "modal_price": float,
            "min_price": float,
            "max_price": float,
            "avg_price": float,       # (min+max)/2 approx
            "market": str,
            "commodity": str,
            "variety": str
        }

    Example:
        data = get_latest_prices("Kanpur", "Potato", "Jyoti")
        # {"modal_price": 2750, "min_price": 2500, "max_price": 3000, ...}
    """
    where, params = _build_where_clause(
        market=market,
        commodity=commodity,
        variety=variety,
    )

    # Latest date ka record
    query = f"""
        SELECT
            arrival_date,
            market,
            commodity,
            variety,
            modal_price,
            min_price,
            max_price
        FROM market_prices
        {where}
        ORDER BY arrival_date DESC
        LIMIT 1
    """

    row = fetch_one(query, params)

    if not row:
        logger.debug(
            f"Latest price not found: market={market}, "
            f"commodity={commodity}, variety={variety}"
        )
        return None

    # Average = (min + max) / 2 (agar dono available hain)
    avg = None
    if row["min_price"] is not None and row["max_price"] is not None:
        avg = (row["min_price"] + row["max_price"]) / 2

    return {
        "arrival_date": row["arrival_date"],
        "market": row["market"],
        "commodity": row["commodity"],
        "variety": row["variety"],
        "modal_price": row["modal_price"],
        "min_price": row["min_price"],
        "max_price": row["max_price"],
        "avg_price": avg,
    }


# ============================================================
# SECTION 4: PRICE TREND (Line Chart)
# ============================================================
# Historical trend: date-wise modal price.
# Frontend pe line chart banega.
# ============================================================

def get_price_trend(
    market: str,
    commodity: str,
    variety: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 365,
) -> list[dict]:
    """
    Historical price trend return karta hai (date-wise modal price).

    Args:
        market: Mandi name.
        commodity: Commodity name.
        variety: Variety (optional).
        start_date: YYYY-MM-DD (optional).
        end_date: YYYY-MM-DD (optional).
        limit: Max records (default 365 = 1 saal).

    Returns:
        list[dict]: [
            {"date": "2026-09-13", "modal_price": 2750.0,
             "min_price": 2500.0, "max_price": 3000.0},
            ...
        ]

    Frontend line chart ke liye ready data.
    """
    where, params = _build_where_clause(
        market=market,
        commodity=commodity,
        variety=variety,
        start_date=start_date,
        end_date=end_date,
    )

    query = f"""
        SELECT
            arrival_date AS date,
            modal_price,
            min_price,
            max_price
        FROM market_prices
        {where}
        ORDER BY arrival_date ASC
        LIMIT ?
    """

    rows = fetch_all(query, params + [limit])

    logger.debug(f"Price trend: {len(rows)} records for {market}/{commodity}")

    return rows


# ============================================================
# SECTION 5: MIN/MAX TREND (Comparison Chart)
# ============================================================
# Min/Max comparison ke liye — same as price trend but
# clearly labelled. Frontend pe separate chart ya overlay.
# ============================================================

def get_min_max_trend(
    market: str,
    commodity: str,
    variety: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 365,
) -> list[dict]:
    """
    Min aur Max price trend (comparison chart ke liye).

    NOTE: Yahan same data hai jo price_trend me hai, lekin
    semantic separation ke liye alag function rakha hai.
    Frontend alag chart bana sakta hai.

    Returns:
        list[dict]: [
            {"date": "...", "min_price": ..., "max_price": ...},
            ...
        ]
    """
    where, params = _build_where_clause(
        market=market,
        commodity=commodity,
        variety=variety,
        start_date=start_date,
        end_date=end_date,
    )

    query = f"""
        SELECT
            arrival_date AS date,
            min_price,
            max_price
        FROM market_prices
        {where}
        ORDER BY arrival_date ASC
        LIMIT ?
    """

    rows = fetch_all(query, params + [limit])

    logger.debug(f"Min/Max trend: {len(rows)} records for {market}/{commodity}")

    return rows


# ============================================================
# SECTION 6: MONTHLY MOVEMENT (Bar Chart)
# ============================================================
# Monthly average modal price — bar chart ke liye.
# Ye seasonality aur long-term trend dikhata hai.
# ============================================================

def get_monthly_movement(
    market: str,
    commodity: str,
    variety: Optional[str] = None,
    months: int = 12,
) -> list[dict]:
    """
    Monthly average modal price return karta hai (bar chart ke liye).

    Args:
        market: Mandi name.
        commodity: Commodity name.
        variety: Variety (optional).
        months: Kitne mahine ka data (default 12).

    Returns:
        list[dict]: [
            {"month": "2026-01", "avg_modal_price": 2650.0, "record_count": 22},
            {"month": "2026-02", "avg_modal_price": 2700.0, "record_count": 24},
            ...
        ]
    """
    where, params = _build_where_clause(
        market=market,
        commodity=commodity,
        variety=variety,
    )

    # SQLite me substr() se YYYY-MM nikaal sakte hain
    query = f"""
        SELECT
            substr(arrival_date, 1, 7) AS month,
            AVG(modal_price) AS avg_modal_price,
            COUNT(*) AS record_count,
            MIN(modal_price) AS min_modal,
            MAX(modal_price) AS max_modal
        FROM market_prices
        {where}
        GROUP BY month
        ORDER BY month DESC
        LIMIT ?
    """

    rows = fetch_all(query, params + [months])

    # Frontend pe chronological order me chahiye (purana → naya)
    rows.reverse()

    # Round avg to 2 decimals
    for row in rows:
        if row.get("avg_modal_price") is not None:
            row["avg_modal_price"] = round(row["avg_modal_price"], 2)

    logger.debug(f"Monthly movement: {len(rows)} months for {market}/{commodity}")

    return rows


# ============================================================
# SECTION 7: MARKET COMPARISON
# ============================================================
# Same commodity ke different markets ka comparison.
# User ka sawaal: "Kanpur me aloo ka rate X hai, Lucknow me kya?"
# ============================================================

def get_market_comparison(
    commodity: str,
    state: Optional[str] = None,
    variety: Optional[str] = None,
    days: int = 7,
) -> list[dict]:
    """
    Same commodity ke different markets ka latest comparison.

    Args:
        commodity: Commodity name (mandatory).
        state: Optional state filter.
        variety: Optional variety filter.
        days: Kitne recent din ka data (default 7).

    Returns:
        list[dict]: [
            {
                "market": "Kanpur",
                "district": "Kanpur Nagar",
                "state": "Uttar Pradesh",
                "latest_date": "2026-09-19",
                "modal_price": 2750.0,
                "min_price": 2500.0,
                "max_price": 3000.0,
                "avg_modal": 2700.0
            },
            ...
        ]
    """
    # Recent date cutoff
    cutoff_date = (date.today() - timedelta(days=days)).strftime("%Y-%m-%d")

    conditions = ["commodity = ?", "arrival_date >= ?"]
    params = [commodity, cutoff_date]

    if state:
        conditions.append("state = ?")
        params.append(state)
    if variety:
        conditions.append("variety = ?")
        params.append(variety)

    where = "WHERE " + " AND ".join(conditions)

    # Har market ka latest record
    query = f"""
        SELECT
            market,
            district,
            state,
            commodity,
            variety,
            MAX(arrival_date) AS latest_date,
            AVG(modal_price) AS avg_modal,
            MIN(min_price) AS min_price,
            MAX(max_price) AS max_price
        FROM market_prices
        {where}
        GROUP BY market, district, state, commodity, variety
        ORDER BY avg_modal DESC
    """

    rows = fetch_all(query, params)

    # Har row me latest modal price nikaalo
    for row in rows:
        latest = fetch_one(
            """
            SELECT modal_price
            FROM market_prices
            WHERE market = ? AND commodity = ? AND arrival_date = ?
            LIMIT 1
            """,
            (row["market"], commodity, row["latest_date"]),
        )
        row["modal_price"] = latest["modal_price"] if latest else None

    # Round avg
    for row in rows:
        if row.get("avg_modal") is not None:
            row["avg_modal"] = round(row["avg_modal"], 2)

    logger.debug(f"Market comparison: {len(rows)} markets for {commodity}")

    return rows


# ============================================================
# SECTION 8: SUMMARY STATS
# ============================================================
# Ek quick summary — total records, date range, markets count.
# Dashboard header pe dikha sakte hain.
# ============================================================

def get_summary_stats() -> dict:
    """
    Dashboard header ke liye summary stats.

    Returns:
        dict: {
            "total_records": int,
            "total_markets": int,
            "total_commodities": int,
            "date_range": {"min": ..., "max": ...},
            "last_sync": {...}  # data_sync_logs se
        }
    """
    # Total records
    total_records = count_rows("market_prices")

    # Distinct markets
    markets_row = fetch_one(
        "SELECT COUNT(DISTINCT market) AS cnt FROM market_prices"
    )
    total_markets = markets_row["cnt"] if markets_row else 0

    # Distinct commodities
    commodities_row = fetch_one(
        "SELECT COUNT(DISTINCT commodity) AS cnt FROM market_prices"
    )
    total_commodities = commodities_row["cnt"] if commodities_row else 0

    # Date range
    date_row = fetch_one(
        "SELECT MIN(arrival_date) as min_date, MAX(arrival_date) as max_date "
        "FROM market_prices"
    )

    # Last sync log (data_sync_logs se)
    last_sync = fetch_one(
        """
        SELECT sync_date, completed_at, status,
               records_fetched, records_inserted, errors
        FROM data_sync_logs
        ORDER BY id DESC
        LIMIT 1
        """
    )

    return {
        "total_records": total_records,
        "total_markets": total_markets,
        "total_commodities": total_commodities,
        "date_range": {
            "min": date_row["min_date"] if date_row else None,
            "max": date_row["max_date"] if date_row else None,
        },
        "last_sync": dict(last_sync) if last_sync else None,
    }


















































# ============================================================
# SECTION 8.5: CASCADING FILTER FUNCTIONS
# ============================================================
# Ye functions dependent dropdowns ke liye values deti hain.
# Jab user State select kare, to Districts sirf us state ke aane chahiye.
# Phir District select kare to Markets sirf us district ke.
# Aur aage bhi.
#
# Ye "cascading filters" ka backend hai.
# ============================================================

def get_districts(state: Optional[str] = None) -> list[str]:
    """
    Districts return karta hai (optional state filter ke saath).

    Args:
        state: State name (agar None, to saare districts).

    Returns:
        list[str]: Sorted district names.
    """
    if state:
        rows = fetch_all(
            "SELECT DISTINCT district FROM market_prices "
            "WHERE state = ? AND district IS NOT NULL AND district != '' "
            "ORDER BY district",
            (state,),
        )
    else:
        rows = fetch_all(
            "SELECT DISTINCT district FROM market_prices "
            "WHERE district IS NOT NULL AND district != '' "
            "ORDER BY district"
        )
    return [row["district"] for row in rows]


def get_markets(
    state: Optional[str] = None,
    district: Optional[str] = None,
) -> list[str]:
    """
    Markets return karta hai (state + district filter ke saath).

    Args:
        state: State name (optional).
        district: District name (optional).

    Returns:
        list[str]: Sorted market names.
    """
    conditions = ["market IS NOT NULL", "market != ''"]
    params = []

    if state:
        conditions.append("state = ?")
        params.append(state)
    if district:
        conditions.append("district = ?")
        params.append(district)

    where = "WHERE " + " AND ".join(conditions)

    rows = fetch_all(
        f"SELECT DISTINCT market FROM market_prices {where} ORDER BY market",
        params,
    )
    return [row["market"] for row in rows]


def get_commodities(
    state: Optional[str] = None,
    district: Optional[str] = None,
    market: Optional[str] = None,
) -> list[str]:
    """
    Commodities return karta hai (state + district + market filter ke saath).

    Args:
        state: State name (optional).
        district: District name (optional).
        market: Market name (optional).

    Returns:
        list[str]: Sorted commodity names.
    """
    conditions = ["commodity IS NOT NULL", "commodity != ''"]
    params = []

    if state:
        conditions.append("state = ?")
        params.append(state)
    if district:
        conditions.append("district = ?")
        params.append(district)
    if market:
        conditions.append("market = ?")
        params.append(market)

    where = "WHERE " + " AND ".join(conditions)

    rows = fetch_all(
        f"SELECT DISTINCT commodity FROM market_prices {where} ORDER BY commodity",
        params,
    )
    return [row["commodity"] for row in rows]


def get_varieties(
    state: Optional[str] = None,
    district: Optional[str] = None,
    market: Optional[str] = None,
    commodity: Optional[str] = None,
) -> list[str]:
    """
    Varieties return karta hai (state + district + market + commodity filter ke saath).

    Args:
        state: State name (optional).
        district: District name (optional).
        market: Market name (optional).
        commodity: Commodity name (optional).

    Returns:
        list[str]: Sorted variety names.
    """
    conditions = ["variety IS NOT NULL", "variety != ''"]
    params = []

    if state:
        conditions.append("state = ?")
        params.append(state)
    if district:
        conditions.append("district = ?")
        params.append(district)
    if market:
        conditions.append("market = ?")
        params.append(market)
    if commodity:
        conditions.append("commodity = ?")
        params.append(commodity)

    where = "WHERE " + " AND ".join(conditions)

    rows = fetch_all(
        f"SELECT DISTINCT variety FROM market_prices {where} ORDER BY variety",
        params,
    )
    return [row["variety"] for row in rows]





















# ============================================================
# SECTION 9: DIRECT RUN — Quick Test
# ============================================================
if __name__ == "__main__":
    print("=" * 65)
    print("KisanBazaar AI — Dashboard Services Test")
    print("=" * 65)

    # Test 1: Filter options
    print("\n--- Test 1: Filter options ---")
    options = get_filter_options()
    print(f"States      : {options['states']}")
    print(f"Markets     : {options['markets']}")
    print(f"Commodities : {options['commodities']}")
    print(f"Date range  : {options['date_range']}")

    # Test 2: Latest prices (jo test data hain)
    print("\n--- Test 2: Latest prices (Kanpur/Potato) ---")
    latest = get_latest_prices("Kanpur", "Potato")
    if latest:
        for k, v in latest.items():
            print(f"  {k}: {v}")
    else:
        print("  ⚠️  Koi record nahi mila (pehle database_loader test chalao)")

    # Test 3: Price trend
    print("\n--- Test 3: Price trend (Kanpur/Potato) ---")
    trend = get_price_trend("Kanpur", "Potato")
    print(f"  Records: {len(trend)}")
    if trend:
        print(f"  First: {trend[0]}")
        print(f"  Last : {trend[-1]}")

    # Test 4: Monthly movement
    print("\n--- Test 4: Monthly movement ---")
    monthly = get_monthly_movement("Kanpur", "Potato")
    print(f"  Months: {len(monthly)}")
    for m in monthly:
        print(f"    {m}")

    # Test 5: Market comparison
    print("\n--- Test 5: Market comparison (Potato) ---")
    comparison = get_market_comparison("Potato")
    print(f"  Markets: {len(comparison)}")
    for c in comparison:
        print(f"    {c}")

    # Test 6: Summary stats
    print("\n--- Test 6: Summary stats ---")
    summary = get_summary_stats()
    for k, v in summary.items():
        print(f"  {k}: {v}")

    print("\n" + "=" * 65)
    print("✅ Dashboard services test complete.")