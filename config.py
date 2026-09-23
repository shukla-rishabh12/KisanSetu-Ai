# ============================================================
# KisanBazaar AI — Central Configuration File
# ============================================================
# Ye file project ki saari settings ek jagah rakhti hai:
#   - Database path
#   - Government API details
#   - AI API key (Gemini / similar)
#   - ML model paths
#   - Scheduler timing
#   - Flask settings
#
# Saari sensitive values .env file se load hoti hain.
# Isse code safe rehta hai aur GitHub pe .env push nahi hoti.
# ============================================================

import os
from pathlib import Path
from dotenv import load_dotenv

# ------------------------------------------------------------
# STEP 1: .env file load karo
# ------------------------------------------------------------
# load_dotenv() .env file ke variables ko environment me daal deta hai.
# Iske baad hum os.getenv() se unhe access kar sakte hain.
load_dotenv()


# ------------------------------------------------------------
# STEP 2: Project ka base path nikalo
# ------------------------------------------------------------
# BASE_DIR = current file (config.py) ka parent folder.
# Ye dynamic hai, isliye project kisi bhi machine pe chale,
# path automatically sahi rahega.
# Example: C:\Users\YourName\kisan setu\kisanbazaar-ai\
BASE_DIR = Path(__file__).resolve().parent


# ============================================================
# SECTION 1: FLASK CONFIGURATION
# ============================================================
class FlaskConfig:
    """Flask app ki settings."""

    # Secret key sessions, CSRF protection, flash messages ke liye.
    # .env me na mile to dev ke liye default use karo.
    SECRET_KEY = os.getenv("FLASK_SECRET_KEY", "dev-secret-key-change-me")

    # Debug mode: development me True, production me False.
    DEBUG = os.getenv("FLASK_DEBUG", "True").lower() == "true"

    # Host aur port
    HOST = os.getenv("FLASK_HOST", "127.0.0.1")
    PORT = int(os.getenv("FLASK_PORT", 5000))

    # Templates aur static folders.
    # Humne global templates/static alag rakhe hain,
    # lekin module-wise bhi hain (dashboard/, ml/, chatbot/).
    # Flask default templates aur static use karega,
    # aur blueprints apne alag paths define karenge.
    TEMPLATE_FOLDER = BASE_DIR / "templates"
    STATIC_FOLDER = BASE_DIR / "static"


# ============================================================
# SECTION 2: DATABASE CONFIGURATION
# ============================================================
class DatabaseConfig:
    """SQLite database settings."""

    # SQLite DB file ka full path.
    # Ye file database/ folder me rahegi.
    DB_FOLDER = BASE_DIR / "database"
    DB_NAME = "kisanbazaar.db"
    DB_PATH = DB_FOLDER / DB_NAME

    # Schema file ka path (tables create karne ke liye).
    SCHEMA_PATH = DB_FOLDER / "schema.sql"

    # Rolling retention: sirf latest 2 saal ka data rakhenge.
    # Purana data daily update ke baad delete ho jayega.
    RETENTION_YEARS = 2


# ============================================================
# SECTION 3: GOVERNMENT MANDI API CONFIGURATION
# ============================================================
class GovernmentAPIConfig:
    """data.gov.in Mandi Price API ki settings."""

    # API ka resource ID (fixed, SRS ke hisaab se).
    RESOURCE_ID = "35985678-0d79-46b4-9ed6-6f13308a1d24"

    # Base URL — resource ID ke saath combine hoga.
    BASE_URL = f"https://api.data.gov.in/resource/{RESOURCE_ID}"

    # API key .env se aayegi (data.gov.in se mili hui key).
    API_KEY = os.getenv("GOVT_API_KEY", "")

    # Pagination: ek request me kitne records.
    # SRS me 2000 diya gaya hai.
    CHUNK_SIZE = 2000

    # Response format (json ya csv). Hum json use karenge.
    FORMAT = "json"

    # Retry settings — network issues ke liye.
    MAX_RETRIES = 5                # Maximum attempts
    RETRY_BACKOFF = 2              # Har retry pe wait kitna badhe (seconds)
    REQUEST_TIMEOUT = 30           # Ek request ka timeout (seconds)

    # Daily update scheduler time.
    # SRS ke example me 11:30 PM diya tha, lekin hum
    # source ke update schedule ke hisaab se rakhenge.
    DAILY_FETCH_HOUR = int(os.getenv("DAILY_FETCH_HOUR", 23))    # 11 PM
    DAILY_FETCH_MINUTE = int(os.getenv("DAILY_FETCH_MINUTE", 30))


# ============================================================
# SECTION 4: ML MODEL CONFIGURATION
# ============================================================
class MLConfig:
    """ML module ki settings (Dashboard ke liye abhi use nahi hoga)."""

    # Models folder jahan .pkl files rahengi.
    MODEL_FOLDER = BASE_DIR / "ml" / "models"

    # Active model ka naam.
    CURRENT_MODEL_NAME = "current_model.pkl"
    CURRENT_MODEL_PATH = MODEL_FOLDER / CURRENT_MODEL_NAME

    # Initial 5-year CSV (sirf pehli training ke liye).
    TRAINING_DATA_FOLDER = BASE_DIR / "training_data"
    HISTORICAL_CSV = TRAINING_DATA_FOLDER / "historical.csv"

    # Forecast: next 10 days.
    FORECAST_DAYS = 10

    # Monthly retraining scheduler (mahine ke 1st din, raat 2 baje).
    RETRAIN_DAY_OF_MONTH = int(os.getenv("RETRAIN_DAY_OF_MONTH", 1))
    RETRAIN_HOUR = int(os.getenv("RETRAIN_HOUR", 2))


# ============================================================
# SECTION 5: AI / CHATBOT CONFIGURATION
# ============================================================
class AIConfig:
    """AI Chatbot / LLM API settings (chatbot module ke liye)."""

    # Groq API key (.env me rahegi)
    API_KEY = os.getenv("GROQ_API_KEY", "")

    # Groq base URL
    BASE_URL = "https://api.groq.com/openai/v1"

    # Model name — Groq pe available models
    # Options: llama-3.3-70b-versatile, llama-3.1-8b-instant, mixtral-8x7b-32768
    MODEL_NAME = os.getenv("AI_MODEL_NAME", "openai/gpt-oss-120b")

    # Chatbot context limits
    MAX_CONTEXT_ROWS = 30
    MAX_TOKENS = 1024


# ============================================================
# SECTION 6: LOGGING CONFIGURATION
# ============================================================
class LoggingConfig:
    """Logging settings — debugging easy banane ke liye."""

    # Logs folder.
    LOG_FOLDER = BASE_DIR / "logs"
    LOG_FILE = LOG_FOLDER / "kisanbazaar.log"

    # Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

    # Log format: time - level - module - message.
    LOG_FORMAT = "%(asctime)s - %(levelname)s - %(name)s - %(message)s"


# ============================================================
# SECTION 7: PATH HELPERS
# ============================================================
def ensure_directories():
    """
    Ye function ensure karta hai ki zaroori folders exist karte hain.
    Agar nahi hain to create kar deta hai.
    Mostly DB folder aur logs folder ke liye useful hai.
    """
    DatabaseConfig.DB_FOLDER.mkdir(parents=True, exist_ok=True)
    LoggingConfig.LOG_FOLDER.mkdir(parents=True, exist_ok=True)
    MLConfig.MODEL_FOLDER.mkdir(parents=True, exist_ok=True)


# ============================================================
# QUICK TEST: Agar is file ko directly run karo to config print ho.
# Run: python config.py
# ============================================================
if __name__ == "__main__":
    print("=" * 50)
    print("KisanBazaar AI — Configuration Check")
    print("=" * 50)
    print(f"Base Dir        : {BASE_DIR}")
    print(f"DB Path         : {DatabaseConfig.DB_PATH}")
    print(f"Schema Path     : {DatabaseConfig.SCHEMA_PATH}")
    print(f"Govt API URL    : {GovernmentAPIConfig.BASE_URL}")
    print(f"Govt API Key    : {'SET' if GovernmentAPIConfig.API_KEY else 'NOT SET'}")
    print(f"Chunk Size      : {GovernmentAPIConfig.CHUNK_SIZE}")
    print(f"Daily Fetch     : {GovernmentAPIConfig.DAILY_FETCH_HOUR}:{GovernmentAPIConfig.DAILY_FETCH_MINUTE:02d}")
    print(f"Model Path      : {MLConfig.CURRENT_MODEL_PATH}")
    print(f"Forecast Days   : {MLConfig.FORECAST_DAYS}")
    print(f"AI API Key      : {'SET' if AIConfig.API_KEY else 'NOT SET'}")
    print(f"Log File        : {LoggingConfig.LOG_FILE}")
    print("=" * 50)
    ensure_directories()
    print("✅ Zaroori folders verify ho gaye.")