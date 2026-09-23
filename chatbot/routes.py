# ============================================================
# KisanBazaar AI — Chatbot Routes (Flask Blueprint)
# ============================================================
# Ye file chatbot ke HTTP endpoints deti hai.
#
# ENDPOINTS:
#   POST /api/chat/insight     → Auto-insight (filters ke baad)
#   POST /api/chat/message     → User ka sawaal, AI reply
#   GET  /api/chat/health      → AI availability check
#   POST /api/chat/session/end → Session close (optional cleanup)
#
# SESSION MANAGEMENT:
#   - Frontend session_id (UUID) generate karta hai
#   - Server session_id ke against context + history store karta hai
#   - Isse har message pe pura context bhejne ki zaroorat nahi
#   - In-memory store (dev ke liye). Production me Redis/DB.
#
# DESIGN:
#   - Routes me koi AI logic nahi — sab services.py me
#   - Context build bhi ek hi baar (insight ke waqt)
#   - Consistent JSON response format
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
from flask import Blueprint, jsonify, request

# Project imports
from chatbot.context import build_context
from chatbot.services import (
    generate_insight,
    generate_reply,
    check_ai_health,
)
from core.logger import get_logger
from core.exceptions import KisanBazaarError, ChatbotError

# Logger
logger = get_logger(__name__)


# ============================================================
# BLUEPRINT SETUP
# ============================================================
# NOTE: Chatbot ka koi static ya template folder nahi hai.
# Chat widget Dashboard/ML ke templates me include hoga.
# Isliye static_folder=None set kiya.

chatbot_bp = Blueprint(
    "chatbot",
    __name__,
    # template_folder="templates",       # ← ye zaroori hai
    static_folder="static",
    static_url_path="/chatbot-assets",
    url_prefix="/api/chat",
)

# ============================================================
# SESSION STORE (in-memory)
# ============================================================
# Simple dict: {session_id: {"context": {...}, "history": [...]}}
#
# LIMITATIONS (acceptable for dev/demo):
#   - Server restart pe saari sessions gayab
#   - Multiple Flask workers ke saath share nahi hoga
#   - Memory me grow karta rahega (cleanup manual)
#
# PRODUCTION ke liye:
#   - Redis ya SQLite/PostgreSQL me store karo
#   - TTL (time-to-live) set karo
# ============================================================

_sessions = {}

# Max sessions to keep in memory (oldest auto-evict)
MAX_SESSIONS = 100

# Max history messages per session (avoid unbounded growth)
MAX_HISTORY = 20


def _get_session(session_id: str) -> dict:
    """
    Session get karta hai. Nahi mila to naya create karta hai.
    """
    if session_id not in _sessions:
        # Evict oldest if too many
        if len(_sessions) >= MAX_SESSIONS:
            oldest_key = next(iter(_sessions))
            del _sessions[oldest_key]
            logger.debug(f"Evicted oldest session: {oldest_key}")

        _sessions[session_id] = {
            "context": None,
            "history": [],
            "created_at": datetime.now().isoformat(timespec="seconds"),
        }

    return _sessions[session_id]


def _add_to_history(session_id: str, role: str, content: str) -> None:
    """
    Session history me ek message add karta hai.
    Max length cross ho to oldest hata dete hain.
    """
    session = _get_session(session_id)
    session["history"].append({
        "role": role,
        "content": content,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
    })

    # Trim if too long (keep last N)
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
# SECTION 1: HEALTH CHECK
# ============================================================

@chatbot_bp.route("/health", methods=["GET"])
def chat_health():
    """
    AI availability check.

    Response:
        {
          "success": true,
          "data": {
            "available": bool,
            "model": str,
            "error": str or null,
            "active_sessions": int
          }
        }
    """
    try:
        health = check_ai_health()
        health["active_sessions"] = len(_sessions)
        return _success(health)
    except Exception as e:
        logger.exception(f"Chat health error: {e}")
        return _error("Health check failed", 500)


# ============================================================
# SECTION 2: AUTO-INSIGHT
# ============================================================

@chatbot_bp.route("/insight", methods=["POST"])
def chat_insight():
    """
    Auto-insight generate karta hai jab user filters apply karta hai.

    Request JSON:
        {
          "session_id": "abc-123",           (optional, generate ho jayega)
          "market": "Kanpur",                (required)
          "commodity": "Potato",             (required)
          "variety": "Jyoti",                (optional)
          "state": "Uttar Pradesh",          (optional)
          "district": "Kanpur Nagar",        (optional)
        }

    Response:
        {
          "success": true,
          "data": {
            "session_id": "abc-123",
            "insight": "...",
            "source": "ai" | "fallback",
            "error": null
          }
        }
    """
    try:
        # --------------------------------------------------------
        # Parse request
        # --------------------------------------------------------
        payload = request.get_json(silent=True) or {}

        market = (payload.get("market") or "").strip()
        commodity = (payload.get("commodity") or "").strip()
        variety = (payload.get("variety") or "").strip() or None
        state = (payload.get("state") or "").strip() or None
        district = (payload.get("district") or "").strip() or None

        if not market:
            return _error("Missing required param: market", 400)
        if not commodity:
            return _error("Missing required param: commodity", 400)

        # Session id — frontend se lo ya generate karo
        session_id = (payload.get("session_id") or "").strip() or str(uuid.uuid4())

        logger.info(
            f"Insight request: session={session_id[:8]}..., "
            f"market={market}, commodity={commodity}, variety={variety}"
        )

        # --------------------------------------------------------
        # Build context (DB se data)
        # --------------------------------------------------------
        context = build_context(
            market=market,
            commodity=commodity,
            variety=variety,
            state=state,
            district=district,
        )

        # --------------------------------------------------------
        # Generate insight (AI call with fallback)
        # --------------------------------------------------------
        result = generate_insight(context)

        # --------------------------------------------------------
        # Store context + insight in session
        # --------------------------------------------------------
        session = _get_session(session_id)
        session["context"] = context
        # Reset history (naya filter = naya session)
        session["history"] = []
        # Pehla assistant message = insight
        _add_to_history(session_id, "assistant", result["text"])

        return _success({
            "session_id": session_id,
            "insight": result["text"],
            "source": result["source"],
            "error": result["error"],
        })

    except ChatbotError as e:
        logger.error(f"Chatbot config error: {e}")
        return _error(str(e), 503, e.details)
    except KisanBazaarError as e:
        logger.warning(f"Known error in insight: {e}")
        return _error(str(e), 400, e.details)
    except Exception as e:
        logger.exception(f"Insight error: {e}")
        return _error("Insight generate nahi ho paya", 500)


# ============================================================
# SECTION 3: USER MESSAGE
# ============================================================

@chatbot_bp.route("/message", methods=["POST"])
def chat_message():
    """
    User ka sawaal ka reply.

    Request JSON:
        {
          "session_id": "abc-123",      (required)
          "message": "Rate kyu badha?"  (required)
        }

    Response:
        {
          "success": true,
          "data": {
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

        if not session_id:
            return _error("Missing required param: session_id", 400)
        if not message:
            return _error("Message khaali hai", 400)

        # Message length limit (safety)
        if len(message) > 500:
            return _error("Message bahut lamba hai (max 500 characters)", 400)

        # --------------------------------------------------------
        # Session check
        # --------------------------------------------------------
        if session_id not in _sessions:
            return _error(
                "Session expire ho gaya. Page refresh karo ya filters dobara apply karo.",
                404,
            )

        session = _sessions[session_id]
        context = session.get("context")

        if not context:
            return _error(
                "Context available nahi hai. Pehle filters apply karo.",
                400,
            )

        logger.info(f"Chat message: session={session_id[:8]}..., msg={message[:50]}...")

        # --------------------------------------------------------
        # Add user message to history (before calling AI)
        # --------------------------------------------------------
        _add_to_history(session_id, "user", message)

        # --------------------------------------------------------
        # Generate reply
        # --------------------------------------------------------
        result = generate_reply(
            context=context,
            user_message=message,
            history=session["history"][:-1],  # current message exclude
        )

        # --------------------------------------------------------
        # Add assistant reply to history
        # --------------------------------------------------------
        _add_to_history(session_id, "assistant", result["text"])

        return _success({
            "reply": result["text"],
            "source": result["source"],
            "error": result["error"],
        })

    except ChatbotError as e:
        logger.error(f"Chatbot config error: {e}")
        return _error(str(e), 503, e.details)
    except KisanBazaarError as e:
        logger.warning(f"Known error in message: {e}")
        return _error(str(e), 400, e.details)
    except Exception as e:
        logger.exception(f"Message error: {e}")
        return _error("Reply generate nahi ho paya", 500)


# ============================================================
# SECTION 4: SESSION END (optional cleanup)
# ============================================================

@chatbot_bp.route("/session/end", methods=["POST"])
def chat_session_end():
    """
    Session ko end karta hai (memory cleanup).

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
            logger.info(f"Session ended: {session_id[:8]}...")

        return _success({"ended": True})

    except Exception as e:
        logger.exception(f"Session end error: {e}")
        return _error("Session end fail", 500)


# ============================================================
# SECTION 5: SESSION INFO (debugging)
# ============================================================

@chatbot_bp.route("/session/info", methods=["GET"])
def chat_session_info():
    """
    Session ka info return karta hai (debugging ke liye).

    Query params:
        session_id (required)
    """
    session_id = request.args.get("session_id", "").strip()

    if not session_id:
        return _error("Missing required param: session_id", 400)

    if session_id not in _sessions:
        return _error("Session not found", 404)

    session = _sessions[session_id]

    # Sirf summary return karo (pura context bada hai)
    return _success({
        "session_id": session_id,
        "created_at": session["created_at"],
        "has_context": session["context"] is not None,
        "history_count": len(session["history"]),
        "context_summary": {
            "market": session["context"].get("market") if session["context"] else None,
            "commodity": session["context"].get("commodity") if session["context"] else None,
        } if session["context"] else None,
    })


# ============================================================
# SECTION 6: DIRECT RUN — Test (optional)
# ============================================================
if __name__ == "__main__":
    from flask import Flask

    test_app = Flask(__name__)
    test_app.register_blueprint(chatbot_bp)

    print("=" * 65)
    print("KisanBazaar AI — Chatbot Routes Test")
    print("=" * 65)
    print("\nTest URLs:")
    print("  http://127.0.0.1:5000/api/chat/health")
    print("\nPOST endpoints (curl se test karo):")
    print("  POST /api/chat/insight")
    print("  POST /api/chat/message")
    print("  POST /api/chat/session/end")
    print("\nCtrl+C se stop karo.")
    print("=" * 65)

    test_app.run(host="127.0.0.1", port=5000, debug=False)