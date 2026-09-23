# ============================================================
# KisanBazaar AI — Assistant Routes (Flask Blueprint)
# ============================================================
# Ye file "Ask AI" — dedicated farming consultant page ke
# HTTP endpoints deti hai.
#
# ENDPOINTS:
#   Page:
#     GET  /assistant                     → Full-page chat UI
#
#   APIs (JSON):
#     POST /api/assistant/message         → User message, AI reply
#     POST /api/assistant/session/end     → Session cleanup
#     GET  /api/assistant/health          → AI availability
#
# DIFFERENCE FROM chatbot/routes.py:
#   - chatbot/routes.py: Market-data aware (Dashboard/ML ke saath)
#   - assistant_routes.py: General farming consultant (no market context)
#
# DESIGN:
#   - Same session pattern (in-memory dict)
#   - Uses chatbot.services.generate_consultant_reply()
# ============================================================

import sys
import uuid
from datetime import datetime
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
from chatbot.services import generate_consultant_reply, check_ai_health
from core.logger import get_logger
from core.exceptions import KisanBazaarError, ChatbotError

# Logger
logger = get_logger(__name__)


# ============================================================
# BLUEPRINT SETUP
# ============================================================
# NOTE: `template_folder` aur `static_folder` chatbot ke same
# hain (chatbot/templates, chatbot/static). But:
#   - Template: assistant/index.html (chatbot/templates/assistant/)
#   - CSS/JS: assistant.css, assistant.js (chatbot/static/chatbot/)
# Unique static URL path — global namespace me alag rakhta hai.

assistant_bp = Blueprint(
    "assistant",
    __name__,
    template_folder="templates",           # chatbot/templates/
    static_folder="static",                # chatbot/static/
    static_url_path="/assistant-assets",   # UNIQUE URL (conflict avoid)
    url_prefix="",
)


# ============================================================
# SESSION STORE (in-memory)
# ============================================================
# Simple dict: {session_id: {"history": [...], "created_at": "..."}}
# Same pattern jaise chatbot/routes.py me.

_sessions = {}
MAX_SESSIONS = 100
MAX_HISTORY = 20


def _get_session(session_id: str) -> dict:
    """Session get karta hai, nahi mila to naya create."""
    if session_id not in _sessions:
        if len(_sessions) >= MAX_SESSIONS:
            oldest_key = next(iter(_sessions))
            del _sessions[oldest_key]

        _sessions[session_id] = {
            "history": [],
            "created_at": datetime.now().isoformat(timespec="seconds"),
        }
    return _sessions[session_id]


def _add_to_history(session_id: str, role: str, content: str) -> None:
    """Session history me message add karta hai (max length trim)."""
    session = _get_session(session_id)
    session["history"].append({
        "role": role,
        "content": content,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
    })
    if len(session["history"]) > MAX_HISTORY:
        session["history"] = session["history"][-MAX_HISTORY:]


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

@assistant_bp.route("/assistant", methods=["GET"])
def assistant_page():
    """
    Assistant page render karta hai.
    URL: /assistant
    Template: chatbot/templates/assistant/index.html
    """
    logger.debug("Assistant page requested")
    return render_template("assistant/index.html")


# ============================================================
# SECTION 2: HEALTH CHECK
# ============================================================

@assistant_bp.route("/api/assistant/health", methods=["GET"])
def assistant_health():
    """
    AI availability check.

    Response:
        {"success": true, "data": {"available": bool, "model": str, ...}}
    """
    try:
        health = check_ai_health()
        health["active_sessions"] = len(_sessions)
        return _success(health)
    except Exception as e:
        logger.exception(f"Assistant health error: {e}")
        return _error("Health check failed", 500)


# ============================================================
# SECTION 3: USER MESSAGE
# ============================================================

@assistant_bp.route("/api/assistant/message", methods=["POST"])
def assistant_message():
    """
    User message ka reply.

    Request JSON:
        {
          "session_id": "abc-123",              (optional)
          "message": "Tamatar me peele patte?"  (required)
        }

    Response:
        {
          "success": true,
          "data": {
            "session_id": "abc-123",
            "reply": "...",
            "source": "ai" | "fallback",
            "error": null
          }
        }
    """
    try:
        payload = request.get_json(silent=True) or {}

        session_id = (payload.get("session_id") or "").strip()
        message = (payload.get("message") or "").strip()

        # Validation
        if not message:
            return _error("Message khaali hai", 400)

        if len(message) > 500:
            return _error("Message bahut lamba hai (max 500 characters)", 400)

        # Session id — frontend se lo ya generate
        if not session_id:
            session_id = str(uuid.uuid4())

        logger.info(
            f"Assistant message: session={session_id[:8]}..., "
            f"msg={message[:50]}..."
        )

        # Get history (before adding current message)
        session = _get_session(session_id)
        history = session["history"][:]

        # Add user message to history
        _add_to_history(session_id, "user", message)

        # Generate reply (no market context)
        result = generate_consultant_reply(
            user_message=message,
            history=history,
        )

        # Add assistant reply to history
        _add_to_history(session_id, "assistant", result["text"])

        return _success({
            "session_id": session_id,
            "reply": result["text"],
            "source": result["source"],
            "error": result["error"],
        })

    except ChatbotError as e:
        logger.error(f"Chatbot config error: {e}")
        return _error(str(e), 503, e.details)
    except KisanBazaarError as e:
        logger.warning(f"Known error: {e}")
        return _error(str(e), 400, e.details)
    except Exception as e:
        logger.exception(f"Assistant message error: {e}")
        return _error("Reply generate nahi ho paya", 500)


# ============================================================
# SECTION 4: SESSION END
# ============================================================

@assistant_bp.route("/api/assistant/session/end", methods=["POST"])
def assistant_session_end():
    """
    Session end (memory cleanup).

    Request JSON:
        {"session_id": "abc-123"}
    """
    try:
        payload = request.get_json(silent=True) or {}
        session_id = (payload.get("session_id") or "").strip()

        if not session_id:
            return _error("Missing required param: session_id", 400)

        if session_id in _sessions:
            del _sessions[session_id]
            logger.info(f"Assistant session ended: {session_id[:8]}...")

        return _success({"ended": True})

    except Exception as e:
        logger.exception(f"Session end error: {e}")
        return _error("Session end fail", 500)


# ============================================================
# SECTION 5: DIRECT RUN — Test
# ============================================================
if __name__ == "__main__":
    from flask import Flask

    test_app = Flask(__name__)
    test_app.register_blueprint(assistant_bp)

    print("=" * 65)
    print("KisanBazaar AI — Assistant Routes Test")
    print("=" * 65)
    print("\nTest URLs:")
    print("  http://127.0.0.1:5000/assistant")
    print("  http://127.0.0.1:5000/api/assistant/health")
    print("\nCtrl+C se stop karo.")
    print("=" * 65)

    test_app.run(host="127.0.0.1", port=5000, debug=False)