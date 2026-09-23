# ============================================================
# KisanBazaar AI — Chatbot Context Builder
# ============================================================
# Ye file DB se saara relevant data collect karke ek
# structured context dict banati hai jo LLM ko diya jayega.
#
# KAAM:
#   1. Latest price snapshot
#   2. Recent prices (last N days) — trend analysis ke liye
#   3. Trend summary (direction, change %, low, high)
#   4. Market comparison (same commodity other mandis me)
#   5. Monthly summary (last 6 months)
#   6. Filter metadata (market, commodity, variety, etc.)
#
# IMPORTANT:
#   - Ye file AI call NAHI karti. Sirf data collect karti hai.
#   - Dashboard ke services.py ke functions reuse karti hai.
#   - Sab kuch DB se aata hai — koi hallucination ka chance nahi.
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
from dashboard import services
from core.logger import get_logger

# Logger
logger = get_logger(__name__)


# ============================================================
# SECTION 1: TREND CALCULATION HELPERS
# ============================================================

def _calculate_trend_summary(trend_data: list[dict]) -> Optional[dict]:
    """
    Trend data se summary nikaalta hai:
      - direction: up / down / stable
      - change_pct: first se last price tak % change
      - low, high: period me min aur max modal price
      - days: kitne din ka data

    Args:
        trend_data: [{"date": "YYYY-MM-DD", "modal_price": float, ...}, ...]

    Returns:
        dict: Trend summary, ya None agar data empty hai.
    """
    if not trend_data or len(trend_data) < 2:
        return None

    # Sirf wahi rows lo jahan modal_price valid ho
    valid = [row for row in trend_data if row.get("modal_price") is not None]
    if len(valid) < 2:
        return None

    prices = [row["modal_price"] for row in valid]
    first_price = prices[0]
    last_price = prices[-1]

    # % change
    if first_price > 0:
        change_pct = ((last_price - first_price) / first_price) * 100.0
    else:
        change_pct = 0.0

    # Direction threshold: 1% se kam change "stable" mana jayega
    if change_pct > 1.0:
        direction = "up"
    elif change_pct < -1.0:
        direction = "down"
    else:
        direction = "stable"

    return {
        "days": len(valid),
        "direction": direction,
        "change_pct": round(change_pct, 2),
        "first_price": first_price,
        "last_price": last_price,
        "low": min(prices),
        "high": max(prices),
    }


def _summarize_recent_prices(
    trend_data: list[dict],
    days: int = 7,
) -> list[dict]:
    """
    Trend data me se last N din ke records return karta hai.
    LLM ko sirf recent data dikhana hai (bahut zyada nahi).

    Args:
        trend_data: Full trend data
        days: Kitne recent din

    Returns:
        list[dict]: Recent records (chronological order)
    """
    if not trend_data:
        return []

    # Last N days
    return trend_data[-days:]


# ============================================================
# SECTION 2: MARKET COMPARISON HELPER
# ============================================================

def _summarize_comparison(comparison_data: list[dict], top_n: int = 5) -> list[dict]:
    """
    Market comparison me se top N markets return karta hai (modal price descending).

    LLM ko 2754 markets nahi dikhane. Sirf top 5 relevant.

    Args:
        comparison_data: Full comparison list
        top_n: Kitne markets

    Returns:
        list[dict]: Top N markets
    """
    if not comparison_data:
        return []

    # Modal price ke hisaab se descending sort
    sorted_data = sorted(
        comparison_data,
        key=lambda x: x.get("modal_price") or 0,
        reverse=True,
    )

    # Sirf relevant fields
    result = []
    for c in sorted_data[:top_n]:
        result.append({
            "market": c.get("market"),
            "district": c.get("district"),
            "state": c.get("state"),
            "commodity": c.get("commodity"),
            "variety": c.get("variety"),
            "modal_price": c.get("modal_price"),
            "min_price": c.get("min_price"),
            "max_price": c.get("max_price"),
            "avg_modal": c.get("avg_modal"),
            "latest_date": c.get("latest_date"),
        })

    return result


# ============================================================
# SECTION 3: MONTHLY SUMMARY HELPER
# ============================================================

def _summarize_monthly(monthly_data: list[dict], last_n: int = 6) -> list[dict]:
    """
    Monthly movement me se last N months return karta hai.

    Args:
        monthly_data: Full monthly list (already chronological)
        last_n: Kitne recent months

    Returns:
        list[dict]: Last N months
    """
    if not monthly_data:
        return []

    return monthly_data[-last_n:]


# ============================================================
# SECTION 4: MAIN CONTEXT BUILDER
# ============================================================

def build_context(
    market: str,
    commodity: str,
    variety: Optional[str] = None,
    state: Optional[str] = None,
    district: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> dict:
    """
    Full context dict build karta hai jo LLM ko diya jayega.

    Steps:
      1. Latest price snapshot
      2. Full price trend (max 90 days — enough for context)
      3. Trend summary (direction, change %)
      4. Recent prices (last 7 din LLM ko dikhane ke liye)
      5. Market comparison (same commodity, top 5 markets)
      6. Monthly summary (last 6 months)

    Args:
        market: Mandi name (required).
        commodity: Commodity name (required).
        variety: Variety (optional).
        state: State filter (optional).
        district: District filter (optional).
        start_date: Optional date range start.
        end_date: Optional date range end.

    Returns:
        dict: {
            "market": str,
            "commodity": str,
            "variety": str or None,
            "state": str or None,
            "district": str or None,
            "latest": {...} or None,
            "trend_summary": {...} or None,
            "recent_prices": [...],
            "market_comparison": [...],
            "monthly_summary": [...],
            "built_at": str,
        }

    Example:
        ctx = build_context("Kanpur", "Potato", variety="Jyoti")
        print(ctx["latest"]["modal_price"])
    """
    logger.info(f"Building context: market={market}, commodity={commodity}, variety={variety}")

    # --------------------------------------------------------
    # Initialize empty context
    # --------------------------------------------------------
    context = {
        "market": market,
        "commodity": commodity,
        "variety": variety,
        "state": state,
        "district": district,
        "latest": None,
        "trend_summary": None,
        "recent_prices": [],
        "market_comparison": [],
        "monthly_summary": [],
        "built_at": datetime.now().isoformat(timespec="seconds"),
    }

    # --------------------------------------------------------
    # STEP 1: Latest price snapshot
    # --------------------------------------------------------
    try:
        latest = services.get_latest_prices(
            market=market,
            commodity=commodity,
            variety=variety,
        )
        context["latest"] = latest
        logger.debug(f"Latest: {latest}")
    except Exception as e:
        logger.warning(f"Latest price fetch fail: {e}")

    # --------------------------------------------------------
    # STEP 2: Price trend (last 90 days for context, ya filter range)
    # --------------------------------------------------------
    try:
        # Default: last 90 days
        if not start_date:
            start_date = (date.today() - timedelta(days=90)).strftime("%Y-%m-%d")

        trend_data = services.get_price_trend(
            market=market,
            commodity=commodity,
            variety=variety,
            start_date=start_date,
            end_date=end_date,
            limit=200,  # context ke liye 200 tak
        )

        # --------------------------------------------------------
        # STEP 3: Trend summary
        # --------------------------------------------------------
        context["trend_summary"] = _calculate_trend_summary(trend_data)

        # --------------------------------------------------------
        # STEP 4: Recent prices (LLM ke liye, last 7 din)
        # --------------------------------------------------------
        context["recent_prices"] = _summarize_recent_prices(trend_data, days=7)

        logger.debug(f"Trend: {context['trend_summary']}, recent: {len(context['recent_prices'])}")

    except Exception as e:
        logger.warning(f"Trend fetch fail: {e}")

    # --------------------------------------------------------
    # STEP 5: Market comparison (top 5 markets)
    # --------------------------------------------------------
    try:
        comparison = services.get_market_comparison(
            commodity=commodity,
            state=state,
            variety=variety,
            days=7,
        )
        context["market_comparison"] = _summarize_comparison(comparison, top_n=5)
        logger.debug(f"Comparison: {len(context['market_comparison'])} markets")

    except Exception as e:
        logger.warning(f"Comparison fetch fail: {e}")

    # --------------------------------------------------------
    # STEP 6: Monthly summary (last 6 months)
    # --------------------------------------------------------
    try:
        monthly = services.get_monthly_movement(
            market=market,
            commodity=commodity,
            variety=variety,
            months=12,  # fetch 12, dikhao 6
        )
        context["monthly_summary"] = _summarize_monthly(monthly, last_n=6)
        logger.debug(f"Monthly: {len(context['monthly_summary'])} months")

    except Exception as e:
        logger.warning(f"Monthly fetch fail: {e}")

    # --------------------------------------------------------
    # Log summary
    # --------------------------------------------------------
    has_data = any([
        context["latest"],
        context["trend_summary"],
        context["market_comparison"],
        context["monthly_summary"],
    ])

    if has_data:
        logger.info(f"✅ Context built successfully for {market}/{commodity}")
    else:
        logger.warning(f"⚠️  Context empty for {market}/{commodity} — data available nahi hai")

    return context


# ============================================================
# SECTION 5: DIRECT RUN — Quick Test
# ============================================================
if __name__ == "__main__":
    import json

    print("=" * 65)
    print("KisanBazaar AI — Context Builder Test")
    print("=" * 65)

    # DB me jo data hai uske hisaab se market/commodity
    # Pehle check karo DB me kya kya hai:
    from database.db import fetch_all

    markets = fetch_all(
        "SELECT DISTINCT market FROM market_prices LIMIT 5"
    )
    commodities = fetch_all(
        "SELECT DISTINCT commodity FROM market_prices LIMIT 5"
    )

    print("\nDB me available markets (sample):")
    for m in markets:
        print(f"  - {m['market']}")

    print("\nDB me available commodities (sample):")
    for c in commodities:
        print(f"  - {c['commodity']}")

    # Ek sample ke saath context build karo
    if markets and commodities:
        test_market = markets[0]["market"]
        test_commodity = commodities[0]["commodity"]

        print(f"\n--- Building context for: {test_market} / {test_commodity} ---\n")

        ctx = build_context(
            market=test_market,
            commodity=test_commodity,
        )

        # Print context summary (full json print na karo, bahut bada hoga)
        print("=== Context Summary ===")
        print(f"Market: {ctx['market']}")
        print(f"Commodity: {ctx['commodity']}")
        print(f"Variety: {ctx['variety']}")
        print(f"\nLatest: {json.dumps(ctx['latest'], indent=2, default=str)}")
        print(f"\nTrend Summary: {json.dumps(ctx['trend_summary'], indent=2, default=str)}")
        print(f"\nRecent Prices ({len(ctx['recent_prices'])} records):")
        for r in ctx["recent_prices"]:
            print(f"  {r}")
        print(f"\nMarket Comparison ({len(ctx['market_comparison'])} markets):")
        for c in ctx["market_comparison"]:
            print(f"  {c}")
        print(f"\nMonthly Summary ({len(ctx['monthly_summary'])} months):")
        for m in ctx["monthly_summary"]:
            print(f"  {m}")
    else:
        print("\n⚠️  DB me data nahi hai. Pehle bootstrap chalao:")
        print("   python data_pipeline/bootstrap.py 7")

    print("\n" + "=" * 65)
    print("✅ Context test complete.")