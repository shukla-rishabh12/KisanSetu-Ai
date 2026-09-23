# ============================================================
# KisanBazaar AI — Dashboard Routes (Flask Blueprint)
# ============================================================
# Ye file Dashboard ke Flask endpoints define karti hai.
#
# ENDPOINTS:
#   Page:
#     GET /dashboard                          → HTML page
#
#   APIs (JSON):
#     GET /api/dashboard/filters              → Filter dropdowns
#     GET /api/dashboard/summary              → Header stats
#     GET /api/dashboard/latest               → Latest price cards
#     GET /api/dashboard/trend                → Price trend (line chart)
#     GET /api/dashboard/monthly              → Monthly movement (bar chart)
#     GET /api/dashboard/comparison           → Market comparison
#     GET /api/dashboard/districts            → Cascading: districts
#     GET /api/dashboard/markets              → Cascading: markets
#     GET /api/dashboard/commodities          → Cascading: commodities
#     GET /api/dashboard/varieties            → Cascading: varieties
#     GET /api/dashboard/health               → Health check
# ============================================================

import sys
from pathlib import Path
from flask import (
    Blueprint,
    render_template,
    jsonify,
    request,
)


# ------------------------------------------------------------
# PATH FIX
# ------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# Project imports
from dashboard import services
from core.logger import get_logger
from core.exceptions import KisanBazaarError

# Logger
logger = get_logger(__name__)


# ============================================================
# BLUEPRINT SETUP
# ============================================================
# IMPORTANT: static_url_path UNIQUE hona chahiye!
#
# Kyun?
#   - Main app (app.py) ka static folder: kisanbazaar-ai/static/
#     → URL: /static/...
#   - Dashboard blueprint ka static folder: dashboard/static/
#     → Agar default rakhein to URL bhi /static/... hoga
#     → DONO CONFLICT karenge, CSS load nahi hoga!
#
# Solution: Blueprint ko alag URL do → /dashboard-assets/...
# Isse main app aur dashboard alag-alag static serve karenge.
# ============================================================

dashboard_bp = Blueprint(
    "dashboard",
    __name__,
    template_folder="templates",
    static_folder="static",
    static_url_path="/dashboard-assets",
    url_prefix="",
)
# ============================================================
# ERROR/SUCCESS RESPONSE HELPERS
# ============================================================

def _error_response(message: str, status_code: int = 400, details: dict = None):
    payload = {
        "success": False,
        "error": message,
    }
    if details:
        payload["details"] = details
    return jsonify(payload), status_code


def _success_response(data, status_code: int = 200):
    return jsonify({
        "success": True,
        "data": data,
    }), status_code


# ============================================================
# SECTION 1: PAGE ROUTE
# ============================================================

@dashboard_bp.route("/dashboard", methods=["GET"])
def dashboard_page():
    """
    Dashboard ka main HTML page render karta hai.
    URL: /dashboard
    """
    logger.debug("Dashboard page requested")

    try:
        filter_options = services.get_filter_options()
        summary = services.get_summary_stats()
    except Exception as e:
        logger.exception(f"Filter options fetch failed: {e}")
        filter_options = {}
        summary = {}

    return render_template(
        "dashboard/index.html",
        filter_options=filter_options,
        summary=summary,
    )


# ============================================================
# SECTION 2: FILTER OPTIONS API
# ============================================================

@dashboard_bp.route("/api/dashboard/filters", methods=["GET"])
def api_filters():
    try:
        data = services.get_filter_options()
        return _success_response(data)
    except Exception as e:
        logger.exception(f"Filters API error: {e}")
        return _error_response("Failed to fetch filter options", 500)


# ============================================================
# SECTION 3: SUMMARY STATS API
# ============================================================

@dashboard_bp.route("/api/dashboard/summary", methods=["GET"])
def api_summary():
    try:
        data = services.get_summary_stats()
        return _success_response(data)
    except Exception as e:
        logger.exception(f"Summary API error: {e}")
        return _error_response("Failed to fetch summary", 500)


# ============================================================
# SECTION 4: LATEST PRICES API
# ============================================================

@dashboard_bp.route("/api/dashboard/latest", methods=["GET"])
def api_latest():
    market = request.args.get("market", "").strip()
    commodity = request.args.get("commodity", "").strip()
    variety = request.args.get("variety", "").strip() or None

    if not market:
        return _error_response("Missing required param: market", 400)
    if not commodity:
        return _error_response("Missing required param: commodity", 400)

    try:
        data = services.get_latest_prices(market, commodity, variety)
        if data is None:
            return _error_response(
                "No data found for the selected filters",
                404,
                {"market": market, "commodity": commodity, "variety": variety},
            )
        return _success_response(data)
    except KisanBazaarError as e:
        logger.warning(f"Latest API known error: {e}")
        return _error_response(str(e), 400, e.details)
    except Exception as e:
        logger.exception(f"Latest API error: {e}")
        return _error_response("Failed to fetch latest prices", 500)


# ============================================================
# SECTION 5: PRICE TREND API
# ============================================================

@dashboard_bp.route("/api/dashboard/trend", methods=["GET"])
def api_trend():
    market = request.args.get("market", "").strip()
    commodity = request.args.get("commodity", "").strip()
    variety = request.args.get("variety", "").strip() or None
    start_date = request.args.get("start_date", "").strip() or None
    end_date = request.args.get("end_date", "").strip() or None

    try:
        limit = int(request.args.get("limit", 365))
        limit = min(max(limit, 1), 2000)
    except (ValueError, TypeError):
        return _error_response("Invalid limit (must be integer)", 400)

    if not market:
        return _error_response("Missing required param: market", 400)
    if not commodity:
        return _error_response("Missing required param: commodity", 400)

    try:
        data = services.get_price_trend(
            market=market, commodity=commodity, variety=variety,
            start_date=start_date, end_date=end_date, limit=limit,
        )
        return _success_response(data)
    except Exception as e:
        logger.exception(f"Trend API error: {e}")
        return _error_response("Failed to fetch price trend", 500)


# ============================================================
# SECTION 6: MONTHLY MOVEMENT API
# ============================================================

@dashboard_bp.route("/api/dashboard/monthly", methods=["GET"])
def api_monthly():
    market = request.args.get("market", "").strip()
    commodity = request.args.get("commodity", "").strip()
    variety = request.args.get("variety", "").strip() or None

    try:
        months = int(request.args.get("months", 12))
        months = min(max(months, 1), 60)
    except (ValueError, TypeError):
        return _error_response("Invalid months (must be integer)", 400)

    if not market:
        return _error_response("Missing required param: market", 400)
    if not commodity:
        return _error_response("Missing required param: commodity", 400)

    try:
        data = services.get_monthly_movement(
            market=market, commodity=commodity,
            variety=variety, months=months,
        )
        return _success_response(data)
    except Exception as e:
        logger.exception(f"Monthly API error: {e}")
        return _error_response("Failed to fetch monthly movement", 500)


# ============================================================
# SECTION 7: MARKET COMPARISON API
# ============================================================

@dashboard_bp.route("/api/dashboard/comparison", methods=["GET"])
def api_comparison():
    commodity = request.args.get("commodity", "").strip()
    state = request.args.get("state", "").strip() or None
    variety = request.args.get("variety", "").strip() or None

    try:
        days = int(request.args.get("days", 7))
        days = min(max(days, 1), 90)
    except (ValueError, TypeError):
        return _error_response("Invalid days (must be integer)", 400)

    if not commodity:
        return _error_response("Missing required param: commodity", 400)

    try:
        data = services.get_market_comparison(
            commodity=commodity, state=state,
            variety=variety, days=days,
        )
        return _success_response(data)
    except Exception as e:
        logger.exception(f"Comparison API error: {e}")
        return _error_response("Failed to fetch market comparison", 500)


# ============================================================
# SECTION 8: CASCADING FILTER APIs
# ============================================================

@dashboard_bp.route("/api/dashboard/districts", methods=["GET"])
def api_districts():
    state = request.args.get("state", "").strip() or None
    try:
        data = services.get_districts(state=state)
        return _success_response(data)
    except Exception as e:
        logger.exception(f"Districts API error: {e}")
        return _error_response("Failed to fetch districts", 500)


@dashboard_bp.route("/api/dashboard/markets", methods=["GET"])
def api_markets():
    state = request.args.get("state", "").strip() or None
    district = request.args.get("district", "").strip() or None
    try:
        data = services.get_markets(state=state, district=district)
        return _success_response(data)
    except Exception as e:
        logger.exception(f"Markets API error: {e}")
        return _error_response("Failed to fetch markets", 500)


@dashboard_bp.route("/api/dashboard/commodities", methods=["GET"])
def api_commodities():
    state = request.args.get("state", "").strip() or None
    district = request.args.get("district", "").strip() or None
    market = request.args.get("market", "").strip() or None
    try:
        data = services.get_commodities(
            state=state, district=district, market=market
        )
        return _success_response(data)
    except Exception as e:
        logger.exception(f"Commodities API error: {e}")
        return _error_response("Failed to fetch commodities", 500)


@dashboard_bp.route("/api/dashboard/varieties", methods=["GET"])
def api_varieties():
    state = request.args.get("state", "").strip() or None
    district = request.args.get("district", "").strip() or None
    market = request.args.get("market", "").strip() or None
    commodity = request.args.get("commodity", "").strip() or None
    try:
        data = services.get_varieties(
            state=state, district=district,
            market=market, commodity=commodity,
        )
        return _success_response(data)
    except Exception as e:
        logger.exception(f"Varieties API error: {e}")
        return _error_response("Failed to fetch varieties", 500)


# ============================================================
# SECTION 9: HEALTH CHECK
# ============================================================

@dashboard_bp.route("/api/dashboard/health", methods=["GET"])
def api_health():
    from datetime import datetime
    return _success_response({
        "status": "ok",
        "module": "dashboard",
        "timestamp": datetime.now().isoformat(timespec="seconds"),
    })


# ============================================================
# SECTION 10: DIRECT RUN — Test (optional)
# ============================================================
if __name__ == "__main__":
    from flask import Flask
    test_app = Flask(__name__)
    test_app.register_blueprint(dashboard_bp)

    print("=" * 65)
    print("KisanBazaar AI — Dashboard Routes Test")
    print("=" * 65)
    print("\nTest URLs:")
    print("  http://127.0.0.1:5000/dashboard")
    print("  http://127.0.0.1:5000/api/dashboard/health")
    print("\nCtrl+C se stop karo.")
    print("=" * 65)

    test_app.run(host="127.0.0.1", port=5000, debug=False)