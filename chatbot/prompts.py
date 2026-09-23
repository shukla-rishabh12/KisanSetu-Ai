# ============================================================
# KisanBazaar AI — Chatbot Prompts
# ============================================================
# Ye file LLM ke liye prompt templates rakhti hai.
#
# DESIGN PRINCIPLES (SRS se):
#   1. LLM source of truth nahi hai — sirf explainer hai
#   2. Actual prices DB se aate hain, LLM unhe natural language me
#      convert karta hai
#   3. Hallucination rokna — prompt me strict rules hain
#   4. Hinglish output — Indian farmers ke liye accessible
#
# PROMPTS:
#   SYSTEM_PROMPT_INSIGHT      → Auto-insight (market data context)
#   SYSTEM_PROMPT_CHAT         → Chat follow-up (market data context)
#   SYSTEM_PROMPT_CONSULTANT   → Kisan Mitra (no market context, general)
#
# FUNCTIONS:
#   build_insight_prompt(context)              → Auto-insight prompt
#   build_chat_prompt(context, msg, history)   → Chat reply prompt
# ============================================================


# ============================================================
# SYSTEM PROMPT: AUTO-INSIGHT
# ============================================================

SYSTEM_PROMPT_INSIGHT = """You are KisanBazaar AI, a friendly agricultural market assistant for Indian farmers.

Your job: Read the market data provided below and generate a SHORT, CLEAR insight (3-5 sentences).

CRITICAL RULES:
1. Use ONLY the numbers and facts provided in the context. NEVER invent or guess prices, markets, or commodities.
2. If data is missing or insufficient, say "Is filter ke liye zyada data available nahi hai" — do NOT make up numbers.
3. Write in simple Hinglish (Hindi in Roman script + English technical terms).
   Example: "Kanpur mandi me aaj Potato ka modal price ₹2,750 per quintal hai."
4. Structure: Start with the KEY takeaway, then supporting numbers.
5. Be concise — farmers want quick answers, not essays.
6. Highlight trend direction (badh raha / ghat raha / stable) if data shows it.
7. Do NOT use markdown formatting (no **bold**, no bullet points). Plain text only.

OUTPUT: Plain Hinglish text, 3-5 sentences maximum."""


# ============================================================
# SYSTEM PROMPT: CHAT (follow-up conversation)
# ============================================================

SYSTEM_PROMPT_CHAT = """You are KisanBazaar AI, a friendly agricultural market assistant.

You are helping an Indian farmer understand mandi market data that is already displayed on their dashboard.

CRITICAL RULES:
1. Use ONLY the data provided in the context below. NEVER invent or guess prices, trends, or market names.
2. If the farmer asks something not available in the context, respond politely:
   "Ye information mere paas nahi hai. Dashboard me filters change karke try karo."
3. Answer in simple Hinglish (Roman script Hindi + English technical terms).
4. If the farmer asks in pure Hindi (Devanagari script), respond in pure Hindi.
5. If the farmer asks in English, respond in English.
6. Be warm, helpful, and CONCISE. 2-4 sentences unless asked to explain more.
7. Do NOT use markdown formatting. Plain text only.
8. NEVER quote future predicted prices unless they are explicitly in the context. If asked about future, say:
   "Future price prediction ML module me hoga, abhi main sirf current aur historical data ke baare me bata sakta hoon."

AVAILABLE CONTEXT:
- Current market data (recent prices, trend, KPIs)
- Market comparison (other mandis)
- Monthly movement summary
- Previous conversation history

Your responses should make the farmer feel informed and confident about their market decisions."""


# ============================================================
# SYSTEM PROMPT: FARMING CONSULTANT (Kisan Mitra)
# ============================================================
# Ye Assistant page ke liye hai — ek general farming consultant.
# Market data context NAHI hai. Sirf general knowledge.
# ============================================================

SYSTEM_PROMPT_CONSULTANT = """You are Kisan Mitra, a friendly and knowledgeable farming consultant for Indian farmers.

Your role: Help farmers with general agriculture questions — crops, weather, soil, seeds, fertilizers, pests, diseases, government schemes, market basics, and best practices.

CRITICAL RULES:
1. Answer in simple Hinglish (Roman script Hindi + English technical terms).
   Example: "Bhai, tamatar me early blight ki problem ho sakti hai. Iske liye Mancozeb 75% WP use karo."
2. If the farmer asks in pure Hindi (Devanagari), respond in pure Hindi.
3. If the farmer asks in English, respond in English.
4. Be warm, respectful, and helpful. Use "aap" not "tu".
5. Give practical, actionable advice. Not just theory.
6. Keep responses CONCISE (3-5 sentences unless asked to elaborate).
7. Do NOT use markdown formatting (no **bold**, no bullet points). Plain text only.
8. If asked about specific mandi prices or predictions, say:
   "Mandi price aur prediction ke liye Dashboard ya Price Forecast page use karo. Main general farming advice de sakta hoon."
9. If you don't know something, say honestly: "Bhai, is baare me mujhe pura nahi pata. Apne nazdiki Krishi Vigyan Kendra ya agriculture officer se pucho."
10. NEVER make up facts. If unsure, say so.

TOPICS YOU CAN HELP WITH:
- Crop selection, sowing time, harvesting
- Soil health, fertilizers, organic farming
- Pest and disease management
- Irrigation techniques
- Weather impact on crops
- Government schemes (PM-KISAN, Fasal Bima, KCC, etc.)
- Market basics (what is mandi, modal price, MSP, etc.)
- Post-harvest handling and storage
- General farming best practices

You are the farmer's trusted friend and advisor. Be helpful, humble, and honest."""


# ============================================================
# CONTEXT FORMATTER (internal helper)
# ============================================================

def _format_context(context: dict) -> str:
    """
    Context dict ko readable text me convert karta hai.
    LLM ko clean, structured input milta hai.
    """
    if not context:
        return "No context available."

    lines = []

    # Filter context
    lines.append("=== FILTER CONTEXT ===")
    lines.append(f"Market: {context.get('market') or 'Not specified'}")
    lines.append(f"Commodity: {context.get('commodity') or 'Not specified'}")
    if context.get("variety"):
        lines.append(f"Variety: {context['variety']}")
    if context.get("state"):
        lines.append(f"State: {context['state']}")
    if context.get("district"):
        lines.append(f"District: {context['district']}")

    # Latest price snapshot
    latest = context.get("latest")
    if latest:
        lines.append("")
        lines.append("=== LATEST PRICE SNAPSHOT ===")
        lines.append(f"Date: {latest.get('arrival_date', 'N/A')}")
        lines.append(f"Modal Price: ₹{latest.get('modal_price', 'N/A')} per quintal")
        lines.append(f"Min Price: ₹{latest.get('min_price', 'N/A')} per quintal")
        lines.append(f"Max Price: ₹{latest.get('max_price', 'N/A')} per quintal")
        if latest.get("avg_price"):
            lines.append(f"Average: ₹{latest['avg_price']} per quintal")

    # Trend summary
    trend = context.get("trend_summary")
    if trend:
        lines.append("")
        lines.append("=== TREND SUMMARY (recent period) ===")
        lines.append(f"Days analyzed: {trend.get('days', 'N/A')}")
        lines.append(f"Direction: {trend.get('direction', 'N/A')}")
        if trend.get("change_pct") is not None:
            lines.append(f"Change: {trend['change_pct']:+.2f}%")
        if trend.get("low") is not None:
            lines.append(f"Period low: ₹{trend['low']}")
        if trend.get("high") is not None:
            lines.append(f"Period high: ₹{trend['high']}")

    # Recent prices
    recent = context.get("recent_prices") or []
    if recent:
        lines.append("")
        lines.append(f"=== RECENT PRICES (last {len(recent)} days) ===")
        for p in recent[-10:]:
            lines.append(
                f"  {p.get('date', '?')}: "
                f"Modal ₹{p.get('modal_price', '?')}, "
                f"Min ₹{p.get('min_price', '?')}, "
                f"Max ₹{p.get('max_price', '?')}"
            )

    # Market comparison
    comparison = context.get("market_comparison") or []
    if comparison:
        lines.append("")
        lines.append("=== MARKET COMPARISON (same commodity in other mandis) ===")
        for c in comparison[:5]:
            lines.append(
                f"  {c.get('market', '?')} ({c.get('district', '?')}, {c.get('state', '?')}): "
                f"Modal ₹{c.get('modal_price', '?')}, "
                f"Avg ₹{c.get('avg_modal', '?')}, "
                f"as of {c.get('latest_date', '?')}"
            )

    # Monthly summary
    monthly = context.get("monthly_summary") or []
    if monthly:
        lines.append("")
        lines.append("=== MONTHLY AVERAGE (recent months) ===")
        for m in monthly[-6:]:
            lines.append(
                f"  {m.get('month', '?')}: "
                f"Avg ₹{m.get('avg_modal_price', '?')} "
                f"({m.get('record_count', 0)} records)"
            )

    return "\n".join(lines)


def _format_history(history: list) -> str:
    """
    Previous conversation history ko format karta hai.
    """
    if not history:
        return "(no previous conversation)"

    lines = []
    for msg in history[-6:]:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        speaker = "Farmer" if role == "user" else "Assistant"
        lines.append(f"{speaker}: {content}")

    return "\n".join(lines)


# ============================================================
# PUBLIC BUILDER FUNCTIONS
# ============================================================

def build_insight_prompt(context: dict) -> str:
    """
    Auto-insight generate karne ke liye full user prompt banata hai.
    """
    context_text = _format_context(context)

    prompt = f"""Here is the market data for the farmer's current filter:

{context_text}

Generate a 3-5 sentence Hinglish insight for the farmer. Include:
1. Current modal price (in ₹ per quintal)
2. Recent trend direction (badh raha / ghat raha / stable) with approximate change
3. One additional useful observation (min/max range, comparison with other mandis, or monthly pattern)

Remember: ONLY use the data above. Do NOT invent numbers. Respond in plain Hinglish text.

Insight:"""

    return prompt


def build_chat_prompt(
    context: dict,
    user_message: str,
    history: list = None,
) -> str:
    """
    Chat reply ke liye full user prompt banata hai.
    """
    context_text = _format_context(context)
    history_text = _format_history(history or [])

    prompt = f"""CURRENT MARKET DATA:
{context_text}

PREVIOUS CONVERSATION:
{history_text}

FARMER'S QUESTION:
{user_message}

Answer the farmer's question using ONLY the data above. If something is not available in the context, politely say so. Respond in Hinglish (or in the same language as the question). Be concise (2-4 sentences).

Answer:"""

    return prompt


# ============================================================
# DIRECT RUN — Quick Test
# ============================================================
if __name__ == "__main__":
    print("=" * 65)
    print("KisanBazaar AI — Prompts Test")
    print("=" * 65)

    sample_context = {
        "market": "Kanpur",
        "commodity": "Potato",
        "variety": "Jyoti",
        "state": "Uttar Pradesh",
        "district": "Kanpur Nagar",
        "latest": {
            "arrival_date": "2026-09-19",
            "modal_price": 2750.0,
            "min_price": 2500.0,
            "max_price": 3000.0,
            "avg_price": 2750.0,
        },
        "trend_summary": {
            "days": 7,
            "direction": "up",
            "change_pct": 3.4,
            "low": 2650.0,
            "high": 2800.0,
        },
        "recent_prices": [
            {"date": "2026-09-13", "modal_price": 2650, "min_price": 2400, "max_price": 2900},
            {"date": "2026-09-16", "modal_price": 2700, "min_price": 2450, "max_price": 2950},
            {"date": "2026-09-19", "modal_price": 2750, "min_price": 2500, "max_price": 3000},
        ],
        "market_comparison": [
            {"market": "Lucknow", "district": "Lucknow", "state": "UP",
             "modal_price": 2800, "avg_modal": 2780, "latest_date": "2026-09-19"},
        ],
        "monthly_summary": [
            {"month": "2026-08", "avg_modal_price": 2650, "record_count": 22},
            {"month": "2026-09", "avg_modal_price": 2720, "record_count": 18},
        ],
    }

    print("\n--- INSIGHT USER PROMPT ---")
    print(build_insight_prompt(sample_context))

    print("\n" + "=" * 65)
    print("--- CHAT USER PROMPT ---")
    print(build_chat_prompt(
        context=sample_context,
        user_message="Rate kyu badh raha hai?",
    ))

    print("\n" + "=" * 65)
    print("--- CONSULTANT PROMPT (preview) ---")
    print(SYSTEM_PROMPT_CONSULTANT[:300] + "...")

    print("\n" + "=" * 65)
    print("✅ Prompts test complete.")