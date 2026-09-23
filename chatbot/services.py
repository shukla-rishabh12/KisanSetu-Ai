# ============================================================
# KisanBazaar AI — Chatbot Services (Groq AI Integration)
# ============================================================
# Ye file actual Groq AI API call karti hai.
#
# KAAM:
#   1. Groq client configure karna
#   2. Auto-insight generate karna (filters apply hone pe)
#   3. Chat reply generate karna (user ke sawaal pe)
#   4. Fallback template (agar AI fail ho)
#   5. Response cleanup (markdown hatana)
#
# DESIGN:
#   - LLM sirf EXPLAINER hai, source of truth nahi.
#   - Actual data DB se aata hai (context.py), LLM use natural
#     language me convert karta hai.
#   - Har function me fallback — AI fail ho to bhi user ko response mile.
#
# USAGE:
#   from chatbot.services import generate_insight, generate_reply
#   insight = generate_insight(context)
#   reply = generate_reply(context, "Rate kyu badha?", history=[])
# ============================================================

import sys
import re
import time
from pathlib import Path
from typing import Optional

# ------------------------------------------------------------
# PATH FIX
# ------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# Project imports
from config import AIConfig
from core.logger import get_logger
from core.exceptions import ChatbotError
from chatbot.prompts import (
    SYSTEM_PROMPT_INSIGHT,
    SYSTEM_PROMPT_CHAT,
    SYSTEM_PROMPT_CONSULTANT,
    build_insight_prompt,
    build_chat_prompt,
)
# Logger
logger = get_logger(__name__)


# ============================================================
# SECTION 1: GROQ CLIENT (lazy init)
# ============================================================
# Groq client ko lazily initialize karta hai.
# Fast inference, OpenAI-compatible API.
# ============================================================

_groq_client = None


def _get_groq_client():
    """
    Groq client ko lazily initialize karta hai.

    Returns:
        Configured Groq client, ya None agar setup fail ho.

    Raises:
        ChatbotError: Agar API key missing ho.
    """
    global _groq_client

    if _groq_client is not None:
        return _groq_client

    # API key check
    if not AIConfig.API_KEY:
        raise ChatbotError(
            "Groq API key missing hai. .env me GROQ_API_KEY set karo.",
            details={"env_var": "GROQ_API_KEY"},
        )

    try:
        from groq import Groq

        _groq_client = Groq(api_key=AIConfig.API_KEY)
        logger.info(f"✅ Groq client initialized: {AIConfig.MODEL_NAME}")
        return _groq_client

    except ImportError as e:
        raise ChatbotError(
            f"groq library install nahi hai: {e}. Chalao: pip install groq",
            details={"import_error": str(e)},
        )
    except Exception as e:
        raise ChatbotError(
            f"Groq setup fail hua: {e}",
            details={"error": str(e)},
        )


# ============================================================
# SECTION 2: RESPONSE CLEANUP
# ============================================================

def _clean_response(text: str) -> str:
    """
    LLM response ko cleanup karta hai:
      - Extra whitespace trim
      - Markdown bold (**text**) hatao
      - Markdown italic hatao
      - Bullet points (*, -) hatao
      - Numbered lists (1., 2.) ko natural text me convert
      - Extra blank lines hatao

    Kyunki chat widget plain text render karta hai, markdown
    symbols raw dikhte hain — isliye hata dete hain.

    Args:
        text: Raw LLM response.

    Returns:
        str: Cleaned text.
    """
    if not text:
        return ""

    # Trim
    text = text.strip()

    # Markdown bold/italic hatao: **text**, __text__, *text*, _text_
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"__(.+?)__", r"\1", text)
    text = re.sub(r"(?<!\w)\*(.+?)\*(?!\w)", r"\1", text)
    text = re.sub(r"(?<!\w)_(.+?)_(?!\w)", r"\1", text)

    # Bullet points hatao: "* item" ya "- item"
    text = re.sub(r"^\s*[\*\-]\s+", "", text, flags=re.MULTILINE)

    # Numbered lists ko natural me convert: "1. item" → "item"
    text = re.sub(r"^\s*\d+\.\s+", "", text, flags=re.MULTILINE)

    # Inline backticks hatao
    text = text.replace("`", "")

    # Multiple blank lines ko single blank line me
    text = re.sub(r"\n\s*\n\s*\n+", "\n\n", text)

    # Trim again
    text = text.strip()

    return text


# ============================================================
# SECTION 3: FALLBACK TEMPLATES
# ============================================================
# Jab AI fail ho (network, rate limit, API down), to hum
# template-based response dete hain taaki user ko kuch mile.
# ============================================================

def _fallback_insight(context: dict) -> str:
    """
    AI fail hone pe template-based insight.
    Sirf DB data se banta hai, koi hallucination nahi.
    """
    market = context.get("market", "?")
    commodity = context.get("commodity", "?")
    latest = context.get("latest")
    trend = context.get("trend_summary")

    parts = []

    if latest:
        parts.append(
            f"{market} mandi me {commodity} ka modal price "
            f"₹{latest.get('modal_price', '?')} per quintal hai "
            f"(as of {latest.get('arrival_date', '?')})."
        )
        min_p = latest.get("min_price")
        max_p = latest.get("max_price")
        if min_p is not None and max_p is not None:
            parts.append(
                f"Rate ₹{min_p} se ₹{max_p} per quintal ke beech chal raha hai."
            )
    else:
        parts.append(f"{market} mandi me {commodity} ka latest data available nahi hai.")

    if trend:
        direction_map = {"up": "badh raha", "down": "ghat raha", "stable": "stable chal raha"}
        dir_text = direction_map.get(trend.get("direction"), "chal raha")
        change = trend.get("change_pct")
        if change is not None:
            parts.append(
                f"Pichhle {trend.get('days', '?')} din me price {change:+.2f}% {dir_text} hai."
            )

    parts.append("(Note: AI abhi busy hai, ye summary DB data se banayi gayi hai.)")

    return " ".join(parts)


def _fallback_reply(context: dict, user_message: str) -> str:
    """
    AI fail hone pe template-based reply.
    """
    # Basic keyword match karke kuch helpful de dete hain
    msg_lower = user_message.lower()

    if any(kw in msg_lower for kw in ["price", "rate", "kitna", "keemat", "bhav"]):
        latest = context.get("latest")
        market = context.get("market", "?")
        commodity = context.get("commodity", "?")
        if latest:
            return (
                f"{market} mandi me {commodity} ka modal price "
                f"₹{latest.get('modal_price', '?')} per quintal hai "
                f"(as of {latest.get('arrival_date', '?')}). "
                f"(AI busy hai, ye direct DB se answer hai.)"
            )

    if any(kw in msg_lower for kw in ["trend", "badh", "ghat", "gir", "up", "down"]):
        trend = context.get("trend_summary")
        if trend:
            direction_map = {"up": "badh raha", "down": "ghat raha", "stable": "stable"}
            return (
                f"Recent trend: {direction_map.get(trend.get('direction'), '?')} hai. "
                f"Change: {trend.get('change_pct', 0):+.2f}% over {trend.get('days', '?')} days. "
                f"(AI busy hai, ye direct DB se answer hai.)"
            )

    return (
        "AI assistant abhi busy hai. Thodi der me try karo. "
        "Tab tak dashboard pe data dekh sakte ho."
    )


# ============================================================
# SECTION 4: INSIGHT GENERATION (Groq)
# ============================================================

def generate_insight(context: dict, max_retries: int = 2) -> dict:
    """
    Auto-insight generate karta hai (Apply Filters ke baad).

    Args:
        context: Context dict (context.py se).
        max_retries: AI fail hone pe kitni baar try karna.

    Returns:
        dict: {
            "text": str,
            "source": "ai" | "fallback",
            "error": str or None,
        }
    """
    if not context:
        return {
            "text": "Is filter ke liye koi data available nahi hai.",
            "source": "fallback",
            "error": "empty context",
        }

    # --------------------------------------------------------
    # Try AI generation with retry
    # --------------------------------------------------------
    for attempt in range(1, max_retries + 1):
        try:
            client = _get_groq_client()
            prompt = build_insight_prompt(context)

            logger.debug(f"Groq insight call (attempt {attempt})...")

            # Groq call (OpenAI-compatible)
            response = client.chat.completions.create(
                model=AIConfig.MODEL_NAME,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT_INSIGHT},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
                max_tokens=300,
                top_p=0.9,
            )

            # Extract text
            text = ""
            if response and response.choices and len(response.choices) > 0:
                text = response.choices[0].message.content or ""

            if text:
                cleaned = _clean_response(text)
                if cleaned:
                    logger.info(f"✅ AI insight generated ({len(cleaned)} chars)")
                    return {
                        "text": cleaned,
                        "source": "ai",
                        "error": None,
                    }

            logger.warning(f"Attempt {attempt}: empty response from AI")

        except ChatbotError as e:
            # Configuration error — retry useless
            logger.error(f"Chatbot config error: {e}")
            return {
                "text": _fallback_insight(context),
                "source": "fallback",
                "error": str(e),
            }

        except Exception as e:
            logger.warning(f"AI insight attempt {attempt} failed: {e}")
            if attempt < max_retries:
                time.sleep(1.5 * attempt)

    # --------------------------------------------------------
    # All retries failed — fallback
    # --------------------------------------------------------
    logger.warning("AI insight failed after retries — using fallback")
    return {
        "text": _fallback_insight(context),
        "source": "fallback",
        "error": "AI unavailable",
    }


# ============================================================
# SECTION 5: CHAT REPLY GENERATION (Groq)
# ============================================================

def generate_reply(
    context: dict,
    user_message: str,
    history: list = None,
    max_retries: int = 2,
) -> dict:
    """
    User ke sawaal ka reply generate karta hai.

    Args:
        context: Context dict.
        user_message: Farmer ka sawaal.
        history: Previous conversation [{"role", "content"}, ...]
        max_retries: AI fail hone pe retries.

    Returns:
        dict: {
            "text": str,
            "source": "ai" | "fallback",
            "error": str or None,
        }
    """
    if not user_message or not user_message.strip():
        return {
            "text": "Kuch likho to sahi. 🙂",
            "source": "fallback",
            "error": "empty message",
        }

    # --------------------------------------------------------
    # Try AI generation with retry
    # --------------------------------------------------------
    for attempt in range(1, max_retries + 1):
        try:
            client = _get_groq_client()
            prompt = build_chat_prompt(
                context=context,
                user_message=user_message,
                history=history or [],
            )

            logger.debug(f"Groq chat call (attempt {attempt})...")

            response = client.chat.completions.create(
                model=AIConfig.MODEL_NAME,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT_CHAT},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.4,
                max_tokens=400,
                top_p=0.9,
            )

            # Extract text
            text = ""
            if response and response.choices and len(response.choices) > 0:
                text = response.choices[0].message.content or ""

            if text:
                cleaned = _clean_response(text)
                if cleaned:
                    logger.info(f"✅ AI reply generated ({len(cleaned)} chars)")
                    return {
                        "text": cleaned,
                        "source": "ai",
                        "error": None,
                    }

            logger.warning(f"Attempt {attempt}: empty reply from AI")

        except ChatbotError as e:
            logger.error(f"Chatbot config error: {e}")
            return {
                "text": _fallback_reply(context, user_message),
                "source": "fallback",
                "error": str(e),
            }

        except Exception as e:
            logger.warning(f"AI reply attempt {attempt} failed: {e}")
            if attempt < max_retries:
                time.sleep(1.5 * attempt)

    # --------------------------------------------------------
    # All retries failed — fallback
    # --------------------------------------------------------
    logger.warning("AI reply failed after retries — using fallback")
    return {
        "text": _fallback_reply(context, user_message),
        "source": "fallback",
        "error": "AI unavailable",
    }


# ============================================================
# SECTION 6: HEALTH CHECK
# ============================================================














# ============================================================
# SECTION 5.5: CONSULTANT REPLY GENERATION (no market context)
# ============================================================
# Ye Assistant page ke liye hai. Market data context nahi chahiye.
# Sirf user ke sawaal aur conversation history.

def generate_consultant_reply(
    user_message: str,
    history: list = None,
    max_retries: int = 2,
) -> dict:
    """
    Farmer consultant reply generate karta hai (no market context).
    
    Args:
        user_message: Farmer ka sawaal.
        history: Previous conversation [{"role", "content"}, ...]
        max_retries: Retry attempts.
    
    Returns:
        dict: {
            "text": str,
            "source": "ai" | "fallback",
            "error": str or None,
        }
    """
    if not user_message or not user_message.strip():
        return {
            "text": "Kuch likhiye to sahi. 🙂",
            "source": "fallback",
            "error": "empty message",
        }
    
    # Build prompt (no market context — sirf history)
    history_text = ""
    if history:
        lines = []
        for msg in history[-8:]:  # last 8 messages
            role = msg.get("role", "user")
            content = msg.get("content", "")
            speaker = "Farmer" if role == "user" else "Kisan Mitra"
            lines.append(f"{speaker}: {content}")
        history_text = "\n".join(lines)
    
    prompt = f"""PREVIOUS CONVERSATION:
{history_text if history_text else "(no previous conversation)"}

FARMER'S QUESTION:
{user_message}

Answer as Kisan Mitra. Be concise (3-5 sentences). Respond in Hinglish (or same language as question).

Answer:"""
    
    # Try AI generation with retry
    for attempt in range(1, max_retries + 1):
        try:
            client = _get_groq_client()
            
            logger.debug(f"Groq consultant call (attempt {attempt})...")
            
            response = client.chat.completions.create(
                model=AIConfig.MODEL_NAME,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT_CONSULTANT},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.6,      # More conversational
                max_tokens=500,
                top_p=0.9,
            )
            
            text = ""
            if response and response.choices and len(response.choices) > 0:
                text = response.choices[0].message.content or ""
            
            if text:
                cleaned = _clean_response(text)
                if cleaned:
                    logger.info(f"✅ Consultant reply ({len(cleaned)} chars)")
                    return {
                        "text": cleaned,
                        "source": "ai",
                        "error": None,
                    }
            
            logger.warning(f"Attempt {attempt}: empty reply")
        
        except ChatbotError as e:
            logger.error(f"Config error: {e}")
            return {
                "text": "AI assistant abhi busy hai. Thodi der me try karein.",
                "source": "fallback",
                "error": str(e),
            }
        
        except Exception as e:
            logger.warning(f"Consultant attempt {attempt} failed: {e}")
            if attempt < max_retries:
                time.sleep(1.5 * attempt)
    
    return {
        "text": "AI assistant abhi busy hai. Thodi der me try karein.",
        "source": "fallback",
        "error": "AI unavailable",
    }





















def check_ai_health() -> dict:
    """
    AI availability check karta hai.
    Frontend isse decide kar sakta hai ki chat available hai ya nahi.

    Returns:
        dict: {"available": bool, "model": str, "error": str}
    """
    if not AIConfig.API_KEY:
        return {
            "available": False,
            "model": None,
            "error": "GROQ_API_KEY not set in .env",
        }

    try:
        _get_groq_client()
        return {
            "available": True,
            "model": AIConfig.MODEL_NAME,
            "error": None,
        }
    except Exception as e:
        return {
            "available": False,
            "model": AIConfig.MODEL_NAME,
            "error": str(e),
        }


# ============================================================
# SECTION 7: DIRECT RUN — Quick Test
# ============================================================
if __name__ == "__main__":
    print("=" * 65)
    print("KisanBazaar AI — Chatbot Services Test (Groq)")
    print("=" * 65)

    # --------------------------------------------------------
    # Step 1: Health check
    # --------------------------------------------------------
    print("\n--- AI Health Check ---")
    health = check_ai_health()
    print(f"Available: {health['available']}")
    print(f"Model: {health['model']}")
    print(f"Error: {health['error']}")

    if not health["available"]:
        print("\n⚠️  Groq API key missing ya invalid.")
        print("   .env me GROQ_API_KEY set karo.")
        print("   https://console.groq.com/keys se free key milti hai.")
        print("\n   Fallback test ke liye aage badh rahe hain...")

    # --------------------------------------------------------
    # Step 2: Sample context (DB se build)
    # --------------------------------------------------------
    print("\n--- Building sample context from DB ---")
    from chatbot.context import build_context
    from database.db import fetch_all

    markets = fetch_all("SELECT DISTINCT market FROM market_prices LIMIT 1")
    commodities = fetch_all("SELECT DISTINCT commodity FROM market_prices LIMIT 1")

    if not markets or not commodities:
        print("⚠️  DB me data nahi hai. Pehle bootstrap chalao.")
        sys.exit(0)

    test_market = markets[0]["market"]
    test_commodity = commodities[0]["commodity"]

    print(f"Test: {test_market} / {test_commodity}")

    context = build_context(
        market=test_market,
        commodity=test_commodity,
    )

    # --------------------------------------------------------
    # Step 3: Insight test
    # --------------------------------------------------------
    print("\n--- Auto-Insight ---")
    insight = generate_insight(context)
    print(f"Source: {insight['source']}")
    print(f"Error: {insight['error']}")
    print(f"\nText:\n{insight['text']}")

    # --------------------------------------------------------
    # Step 4: Chat reply test (if AI available)
    # --------------------------------------------------------
    if health["available"]:
        print("\n--- Chat Reply Test ---")
        question = "Kanpur me potato ka rate kyu badh raha hai?"
        print(f"Q: {question}")

        reply = generate_reply(context, question)
        print(f"Source: {reply['source']}")
        print(f"\nA:\n{reply['text']}")

    print("\n" + "=" * 65)
    print("✅ Chatbot services test complete.")