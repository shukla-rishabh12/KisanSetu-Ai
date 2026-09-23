# ============================================================
# KisanBazaar AI — Database Package
# ============================================================
# Ye file database/ folder ko Python package banati hai.
# Saath hi db.py ke important functions yahan se expose karti hai,
# taaki baaki modules cleanly import kar sakein.
#
# Do tarike se import kar sakte ho:
#   1. from database.db import fetch_all
#   2. from database import fetch_all       ← ye file enable karti hai
# ============================================================

from database.db import (
    # Connection helpers
    get_connection,
    db_session,

    # Initialization
    init_db,

    # Query helpers
    fetch_all,
    fetch_one,
    execute_query,
    insert_one,
    insert_many,

    # Utility
    table_exists,
    count_rows,
)

# __all__ define karta hai ki `from database import *` karne pe
# kaun-kaunse functions import honge. Ye clean code practice hai.
__all__ = [
    "get_connection",
    "db_session",
    "init_db",
    "fetch_all",
    "fetch_one",
    "execute_query",
    "insert_one",
    "insert_many",
    "table_exists",
    "count_rows",
]