
# ============================================================
# KisanBazaar AI — Central Logging Setup
# ============================================================
# ...
# ============================================================

import sys
from pathlib import Path

# ------------------------------------------------------------
# PATH FIX: Project root ko sys.path me add karo.
# Isse file direct run karne pe bhi `from config import ...` kaam kare.
# (`python -m core.logger` chalane pe iski zaroorat nahi, lekin
#  direct `python core/logger.py` chalane pe ye zaroori hai.)
# ------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import logging
from logging.handlers import RotatingFileHandler

# Config se settings import karo
from config import LoggingConfig

# ============================================================
# KisanBazaar AI — Central Logging Setup
# ============================================================
# Ye file poore project ke liye logging configure karti hai.
#
# Features:
#   1. Console + file dono pe logs
#   2. Consistent format (time - level - module - message)
#   3. Log level .env se configurable
#   4. Duplicate handlers avoid (common bug)
#   5. Rotating file handler (log file bahut badi na ho)
#
# USAGE (kisi bhi module me):
#   from core.logger import get_logger
#   logger = get_logger(__name__)
#   logger.info("Ye ek info message hai")
#   logger.error("Kuch galat hua")
# ============================================================

import logging
import sys
from logging.handlers import RotatingFileHandler

# Config se settings import karo
from config import LoggingConfig


# ============================================================
# SECTION 1: INTERNAL STATE
# ============================================================
# Ye flag ensure karta hai ki logging setup sirf EK BAAR ho.
# Agar multiple modules logger import karein, to baar-baar
# handlers add nahi honge (warna same log 3-4 baar print hota hai).
# ============================================================

_LOGGING_CONFIGURED = False


# ============================================================
# SECTION 2: SETUP FUNCTION
# ============================================================

def _setup_logging() -> None:
    """
    Root logger ko configure karta hai.
    Ye function sirf ek baar chalti hai (idempotent).

    Kya karta hai:
      - Logs folder ensure karta hai
      - File handler add karta hai (rotating)
      - Console handler add karta hai
      - Format set karta hai
    """
    global _LOGGING_CONFIGURED

    # Agar pehle se configured hai, to wapas mat karo
    if _LOGGING_CONFIGURED:
        return

    # Logs folder banao (agar nahi hai to)
    LoggingConfig.LOG_FOLDER.mkdir(parents=True, exist_ok=True)

    # Root logger lo
    root_logger = logging.getLogger()

    # Purane handlers hatao (agar koi hain, jaise Flask ka default)
    # Isse duplicate logs avoid hote hain.
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Log level set karo (.env se aata hai)
    log_level = getattr(logging, LoggingConfig.LOG_LEVEL.upper(), logging.INFO)
    root_logger.setLevel(log_level)

    # --------------------------------------------------------
    # Format: time - level - module - message
    # --------------------------------------------------------
    formatter = logging.Formatter(LoggingConfig.LOG_FORMAT)

    # --------------------------------------------------------
    # HANDLER 1: Rotating File Handler
    # --------------------------------------------------------
    # Log file 5 MB se badi ho jaye to naya file ban jayega.
    # Max 3 backup files rakhenge (total ~15 MB).
    # Isse disk space control me rehta hai.
    file_handler = RotatingFileHandler(
        filename=str(LoggingConfig.LOG_FILE),
        maxBytes=5 * 1024 * 1024,   # 5 MB
        backupCount=3,               # kisanbazaar.log.1, .2, .3
        encoding="utf-8",
    )
    file_handler.setLevel(log_level)
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)

    # --------------------------------------------------------
    # HANDLER 2: Console Handler
    # --------------------------------------------------------
    # Terminal pe bhi logs dikhein (development me useful).
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # Mark karo ki configure ho gaya
    _LOGGING_CONFIGURED = True

    # Ek confirmation log (ye file + console dono pe jayega)
    root_logger.info("=" * 55)
    root_logger.info("KisanBazaar AI — Logging initialized")
    root_logger.info(f"Level : {LoggingConfig.LOG_LEVEL}")
    root_logger.info(f"File  : {LoggingConfig.LOG_FILE}")
    root_logger.info("=" * 55)


# ============================================================
# SECTION 3: PUBLIC API — get_logger()
# ============================================================

def get_logger(name: str = __name__) -> logging.Logger:
    """
    Kisi bhi module ke liye logger return karta hai.

    Args:
        name: Logger ka naam. Best practice: `__name__` pass karo.
              Isse pata chalta hai kaunse module se log aaya.

    Returns:
        logging.Logger: Configured logger.

    Example:
        from core.logger import get_logger
        logger = get_logger(__name__)
        logger.info("Data fetch started")
        logger.error("API timeout", exc_info=True)
    """
    # Ensure karo ki logging setup ho chuki hai
    _setup_logging()

    # Us naam ka logger return karo
    # (Root logger ke handlers automatically apply honge)
    return logging.getLogger(name)


# ============================================================
# SECTION 4: DIRECT RUN — Quick Test
# ============================================================
if __name__ == "__main__":
    # Logger lo
    logger = get_logger(__name__)

    # Different levels ke test messages
    logger.debug("Ye debug message hai — sirf DEBUG level pe dikhega")
    logger.info("Ye info message hai — normal operation")
    logger.warning("Ye warning hai — kuch dhyan dene layak hai")
    logger.error("Ye error hai — kuch galat hua")

    # Exception ke saath log karne ka tarika
    try:
        result = 10 / 0
    except ZeroDivisionError:
        logger.exception("Exception caught (traceback bhi log hoga)")

    # Custom context ke saath
    logger.info(f"Log file path: {LoggingConfig.LOG_FILE}")

    print("\n✅ Logging test complete.")
    print(f"   Logs file me bhi gaye: {LoggingConfig.LOG_FILE}")