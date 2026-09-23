# ============================================================
# KisanBazaar AI — ML Routes (Flask Blueprint)
# ============================================================
# Ye file ML Forecast module ke HTTP endpoints deti hai.
#
# ENDPOINTS:
#   Page:
#     GET /forecast                       → HTML page
#
#   APIs (JSON):
#     POST /api/ml/predict                → Main prediction
#     GET  /api/ml/check                  → Data availability check
#     GET  /api/ml/health                 → Health check
#
# BLUEPRINT:
#   - static_url_path="/ml-assets"  (unique — Dashboard/Chatbot se conflict nahi)
#   - url_prefix="" (routes me full path likhenge)
#
# DEPENDENCIES:
#   - ml/services.py (business logic)
#   - ml/predict.py (model)
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

# Flask
from flask import Blueprint, render_template, jsonify, request

# Project imports
from ml import services as ml_services
from dashboard import services as dash_services
from core.logger import get_logger
from core.exceptions import KisanBazaarError, PredictionError, ModelNotFoundError

# Logger
logger = get_logger(__name__)


# ============================================================
# BLUEPRINT SETUP
# ============================================================
# IMPORTANT: static_url_path UNIQUE hona chahiye (Dashboard/Chatbot pattern).
# Warna main app ke /static/ se conflict hoga.

ml_bp = Blueprint(
    "ml",
    __name__,
    template_folder="templates",           # ml/templates/
    static_folder="static",                # ml/static/
    static_url_path="/ml-assets",          # UNIQUE URL
    url_prefix="",
)


# ============================================================
# RESPONSE HELPERS
# ============================================================

def _success(data, status_code: int = 200):
    return jsonify({"success": True, "data": data}), status_code


def _error(message: str, status_code: int = 400, details: dict = None):
    payload = {"success": False, "error": message}
    if details:
        payload["details"] = details
    return jsonify(payload), status_code


# ============================================================
# SECTION 1: PAGE ROUTE
# ============================================================

@ml_bp.route("/forecast", methods=["GET"])
def forecast_page():
    """
    ML Forecast page render karta hai.
    
    NOTE: filter_options yahan fetch NAHI kar rahe.
    JS khud /api/dashboard/filters se laayega (parallel, fast).
    """
    logger.debug("Forecast page requested")
    
    # Default date = kal
    default_date = (date.today() + timedelta(days=1)).strftime("%Y-%m-%d")
    
    return render_template(
        "ml/forecast.html",
        default_date=default_date,
    )


# ============================================================
# SECTION 2: DATA AVAILABILITY CHECK
# ============================================================

@ml_bp.route("/api/ml/check", methods=["GET"])
def api_check():
    """
    Check karta hai ki market/commodity/variety ka data hai ya nahi.
    Frontend isse pre-validate kar sakta hai.
    
    Query params:
        market (required)
        commodity (required)
        variety (optional)
    
    Response:
        {
          "success": true,
          "data": {
            "available": bool,
            "record_count": int,
            "date_range": {...},
            "warning": str or null
          }
        }
    """
    market = request.args.get("market", "").strip()
    commodity = request.args.get("commodity", "").strip()
    variety = request.args.get("variety", "").strip() or None
    
    if not market:
        return _error("Missing required param: market", 400)
    if not commodity:
        return _error("Missing required param: commodity", 400)
    
    try:
        data = ml_services.check_data_availability(market, commodity, variety)
        return _success(data)
    except Exception as e:
        logger.exception(f"Check API error: {e}")
        return _error("Data availability check fail", 500)


# ============================================================
# SECTION 3: MAIN PREDICTION
# ============================================================

@ml_bp.route("/api/ml/predict", methods=["POST"])
def api_predict():
    """
    Main prediction endpoint.
    
    Request JSON:
        {
          "state": "Uttar Pradesh",           (required)
          "district": "Kanpur Nagar",          (required)
          "market": "Kanpur",                  (required)
          "commodity": "Potato",               (required)
          "variety": "Jyoti",                  (optional)
          "start_date": "2026-09-22",          (optional, default: kal)
          "days": 10,                          (optional, default: 10)
          "quantity_kg": 100                   (optional)
        }
    
    Response:
        {
          "success": true,
          "data": {
            "selected_date": {...},
            "forecast": [...],
            "expected_value": {...} or null,
            "data_info": {...},
            "model_info": {...},
            "input": {...},
            "generated_at": "..."
          }
        }
    """
    try:
        payload = request.get_json(silent=True) or {}
        
        # --------------------------------------------------------
        # Parse input
        # --------------------------------------------------------
        state = (payload.get("state") or "").strip()
        district = (payload.get("district") or "").strip()
        market = (payload.get("market") or "").strip()
        commodity = (payload.get("commodity") or "").strip()
        variety = (payload.get("variety") or "").strip() or None
        
        # --------------------------------------------------------
        # Parse date
        # --------------------------------------------------------
        start_date_str = (payload.get("start_date") or "").strip()
        if start_date_str:
            try:
                start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()
            except ValueError:
                return _error(
                    f"Invalid date format: {start_date_str}. Use YYYY-MM-DD.",
                    400,
                )
        else:
            start_date = date.today() + timedelta(days=1)
        
        # --------------------------------------------------------
        # Parse days
        # --------------------------------------------------------
        try:
            days = int(payload.get("days", 10))
        except (ValueError, TypeError):
            return _error("days must be integer", 400)
        
        # --------------------------------------------------------
        # Parse quantity
        # --------------------------------------------------------
        quantity_kg = payload.get("quantity_kg")
        if quantity_kg is not None:
            try:
                quantity_kg = float(quantity_kg)
            except (ValueError, TypeError):
                return _error("quantity_kg must be number", 400)
        
        # --------------------------------------------------------
        # Call service
        # --------------------------------------------------------
        logger.info(
            f"Predict request: {market}/{commodity}/{variety} "
            f"on {start_date} for {days} days, qty={quantity_kg}"
        )
        
        result = ml_services.predict_price(
            state=state,
            district=district,
            market=market,
            commodity=commodity,
            variety=variety,
            start_date=start_date,
            days=days,
            quantity_kg=quantity_kg,
            log_prediction=True,
        )
        
        return _success(result)
    
    except ValueError as e:
        # Input validation errors
        logger.warning(f"Validation error: {e}")
        return _error(str(e), 400)
    
    except ModelNotFoundError as e:
        logger.error(f"Model not found: {e}")
        return _error(
            "ML model available nahi hai. Server se contact karo.",
            503,
            e.details,
        )
    
    except PredictionError as e:
        logger.warning(f"Prediction error: {e}")
        return _error(str(e), 422, e.details)
    
    except KisanBazaarError as e:
        logger.warning(f"Known error: {e}")
        return _error(str(e), 400, e.details)
    
    except Exception as e:
        logger.exception(f"Predict API error: {e}")
        return _error("Prediction fail hui. Logs check karo.", 500)


# ============================================================
# SECTION 4: HEALTH CHECK
# ============================================================

@ml_bp.route("/api/ml/health", methods=["GET"])
def api_health():
    """
    ML module health check.
    
    Response:
        {
          "success": true,
          "data": {
            "status": "ok",
            "model_loaded": bool,
            "model_info": {...} or null,
            "timestamp": "..."
          }
        }
    """
    from ml.predict import _load_model
    
    result = {
        "status": "ok",
        "module": "ml",
        "model_loaded": False,
        "model_info": None,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
    }
    
    try:
        bundle = _load_model()
        result["model_loaded"] = True
        result["model_info"] = {
            "name": bundle.get("model_name", "unknown"),
            "features": len(bundle.get("feature_cols", [])),
            "test_r2": round(bundle.get("test_r2_avg", 0), 4),
            "test_mape": round(bundle.get("test_mape", 0), 2),
        }
    except ModelNotFoundError as e:
        result["status"] = "degraded"
        result["error"] = str(e)
    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)
    
    return _success(result)


# ============================================================
# SECTION 5: DIRECT RUN — Test (optional)
# ============================================================
if __name__ == "__main__":
    from flask import Flask
    
    test_app = Flask(__name__)
    test_app.register_blueprint(ml_bp)
    
    print("=" * 65)
    print("KisanBazaar AI — ML Routes Test")
    print("=" * 65)
    print("\nTest URLs (browser me kholo ya curl karo):")
    print("  GET  http://127.0.0.1:5000/api/ml/health")
    print("  GET  http://127.0.0.1:5000/api/ml/check?market=Kanpur&commodity=Potato")
    print("  POST http://127.0.0.1:5000/api/ml/predict")
    print("  GET  http://127.0.0.1:5000/forecast")
    print("\nCtrl+C se stop karo.")
    print("=" * 65)
    
    test_app.run(host="127.0.0.1", port=5000, debug=False)