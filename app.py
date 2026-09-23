# ============================================================
# KisanBazaar AI — Main Application Entry Point
# ============================================================
# Ye file poore project ka entry point hai.
#
# KAAM:
#   1. Flask app create karna
#   2. Config load karna
#   3. Database initialize karna (tables create)
#   4. Saare blueprints register karna
#   5. Global error handlers set karna
#   6. Home page route add karna
#   7. Scheduler start karna (daily API fetch)
#   8. ML model preload karna (fast predictions)
#   9. App run karna
#
# RUN (development):
#   python app.py
#
# RUN (production, gunicorn):
#   gunicorn --bind 0.0.0.0:$PORT --workers 1 --timeout 120 app:app
#
# BLUEPRINTS:
#   - Dashboard: /dashboard, /api/dashboard/*
#   - ML:        /forecast, /api/ml/*
#   - Chatbot:   /api/chat/*  (market data aware)
#   - Assistant: /assistant, /api/assistant/*  (farming consultant)
# ============================================================

import os
import sys
from pathlib import Path

# ------------------------------------------------------------
# PATH FIX (direct run ke liye)
# ------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# Third-party
from flask import Flask, render_template, jsonify, request

# Project imports
from config import FlaskConfig, DatabaseConfig
from database.db import init_db
from core.logger import get_logger
from core.exceptions import KisanBazaarError

# Logger
logger = get_logger(__name__)


# ============================================================
# SECTION 1: APP FACTORY
# ============================================================

def create_app() -> Flask:
    """
    Flask application create karke configure karta hai.

    Returns:
        Flask: Ready-to-run Flask app.
    """
    logger.info("=" * 60)
    logger.info("KisanBazaar AI — Application starting...")
    logger.info("=" * 60)

    # --------------------------------------------------------
    # STEP 1: Flask app create karo
    # --------------------------------------------------------
    app = Flask(
        __name__,
        template_folder=str(FlaskConfig.TEMPLATE_FOLDER),
        static_folder=str(FlaskConfig.STATIC_FOLDER),
    )

    # Config load karo
    app.secret_key = FlaskConfig.SECRET_KEY
    app.config["DEBUG"] = FlaskConfig.DEBUG

    # --------------------------------------------------------
    # STEP 2: Database initialize karo
    # --------------------------------------------------------
    try:
        init_db()
        logger.info(f"✅ Database ready: {DatabaseConfig.DB_PATH}")
    except Exception as e:
        logger.exception(f"❌ Database init fail: {e}")
        raise

    # --------------------------------------------------------
    # STEP 3: Blueprints register karo
    # --------------------------------------------------------
    # Dashboard module
    from dashboard.routes import dashboard_bp
    app.register_blueprint(dashboard_bp)
    logger.info("✅ Dashboard blueprint registered")

    # Chatbot module (market data aware)
    from chatbot.routes import chatbot_bp
    app.register_blueprint(chatbot_bp)
    logger.info("✅ Chatbot blueprint registered")

    # ML Forecast module
    from ml.routes import ml_bp
    app.register_blueprint(ml_bp)
    logger.info("✅ ML blueprint registered")

    # Assistant module (Kisan Mitra — farming consultant)
    from chatbot.assistant_routes import assistant_bp
    app.register_blueprint(assistant_bp)
    logger.info("✅ Assistant blueprint registered")

    # --------------------------------------------------------
    # STEP 4: Home page route
    # --------------------------------------------------------
    @app.route("/", methods=["GET"])
    def home():
        """Home page — 3 main options ke saath."""
        return render_template("index.html")

    # --------------------------------------------------------
    # STEP 5: Global error handlers
    # --------------------------------------------------------

    @app.errorhandler(KisanBazaarError)
    def handle_kisanbazaar_error(e):
        """Custom exception → JSON error response."""
        logger.warning(f"KisanBazaarError: {e}")
        return jsonify({
            "success": False,
            "error": e.__class__.__name__,
            "message": e.message,
            "details": e.details,
        }), 400

    @app.errorhandler(404)
    def handle_404(e):
        """404 — page ya resource nahi mila."""
        if request.path.startswith("/api/"):
            return jsonify({
                "success": False,
                "error": "NotFound",
                "message": f"API endpoint not found: {request.path}",
            }), 404
        return render_template("errors/404.html"), 404

    @app.errorhandler(500)
    def handle_500(e):
        """500 — internal server error."""
        logger.exception("Internal server error")
        if request.path.startswith("/api/"):
            return jsonify({
                "success": False,
                "error": "InternalServerError",
                "message": "Kuch galat hua server pe. Logs check karo.",
            }), 500
        return render_template("errors/500.html"), 500

    @app.errorhandler(Exception)
    def handle_generic(e):
        """Koi bhi unexpected exception."""
        logger.exception(f"Unhandled exception: {e}")
        if request.path.startswith("/api/"):
            return jsonify({
                "success": False,
                "error": "ServerError",
                "message": str(e),
            }), 500
        return render_template("errors/500.html"), 500
    

























    # --------------------------------------------------------
    # STEP 5.5: Reloader check (scheduler + bootstrap dono ke liye)
    # --------------------------------------------------------
    # Flask debug mode me reloader 2 processes spawn karta hai.
    # Isse scheduler/bootstrap 2 baar start ho jaate hain. Isliye check:
    #   - WERKZEUG_RUN_MAIN env var reloader ke child process me "true" hota hai
    #   - Production (gunicorn) me ye env var nahi hota, so sab chalega
    _should_start_scheduler = (
        not FlaskConfig.DEBUG
        or os.environ.get("WERKZEUG_RUN_MAIN") == "true"
    )

    # --------------------------------------------------------
    # STEP 5.6: Auto-bootstrap (DB empty/stale ho to background me)
    # --------------------------------------------------------
    # Render free tier pe SQLite ephemeral hai. Har restart pe DB
    # khali ho sakti hai. Ye automatically 90-din ka data fetch
    # karta hai background thread me (non-blocking).
    if _should_start_scheduler:
        try:
            from data_pipeline.auto_bootstrap import start_auto_bootstrap_if_needed
            result = start_auto_bootstrap_if_needed(days=90)
            logger.info(f"Auto-bootstrap: {result['action']} — {result['reason']}")
        except Exception as e:
            logger.warning(f"Auto-bootstrap check fail: {e}")

    # --------------------------------------------------------
    # STEP 6: Scheduler start karo (background me)
    # --------------------------------------------------------
    if _should_start_scheduler:
        try:
            from data_pipeline.scheduler import start_scheduler
            start_scheduler()
            logger.info("✅ Scheduler started in background")
        except Exception as e:
            logger.warning(f"Scheduler start nahi ho paya: {e} (app chalega normally)")
    else:
        logger.info("⏸  Scheduler skipped (reloader parent process)")

    # --------------------------------------------------------
    # STEP 7: ML model preload karo (background me)
    # --------------------------------------------------------
    # Model 42MB ka hai, load hone me 3-5 seconds lagte hain.
    # App start pe ek baar load karke memory me rakh dete hain,
    # phir har prediction fast hogi (no reload).
    #
    # NOTE: Reloader parent me skip karo, warna 2 baar load hoga.
    if _should_start_scheduler:
        try:
            from ml.predict import _load_model
            _load_model()
            logger.info("✅ ML model preloaded")
        except Exception as e:
            logger.warning(f"ML model preload fail: {e} (prediction pe load hoga)")

    # --------------------------------------------------------
    # STEP 8: Startup log
    # --------------------------------------------------------
    logger.info("=" * 60)
    logger.info("✅ KisanBazaar AI ready!")
    logger.info(f"   Home      : http://{FlaskConfig.HOST}:{FlaskConfig.PORT}/")
    logger.info(f"   Dashboard : http://{FlaskConfig.HOST}:{FlaskConfig.PORT}/dashboard")
    logger.info(f"   Forecast  : http://{FlaskConfig.HOST}:{FlaskConfig.PORT}/forecast")
    logger.info(f"   Assistant : http://{FlaskConfig.HOST}:{FlaskConfig.PORT}/assistant")
    logger.info("=" * 60)

    return app


# ============================================================
# SECTION 2: MODULE-LEVEL APP INSTANCE
# ============================================================
# Gunicorn `app:app` is line ko import karta hai.
# Flask dev server bhi isi app ko use karta hai.

app = create_app()


# ============================================================
# SECTION 3: DIRECT RUN (development)
# ============================================================

if __name__ == "__main__":
    app.run(
        host=FlaskConfig.HOST,
        port=FlaskConfig.PORT,
        debug=FlaskConfig.DEBUG,
        # use_reloader=False — warna scheduler 2 baar start hota hai
        # (Flask reloader 2 processes banata hai)
        use_reloader=False,
    )