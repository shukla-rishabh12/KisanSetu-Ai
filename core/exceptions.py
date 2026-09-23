# ============================================================
# KisanBazaar AI — Custom Exceptions
# ============================================================
# Ye file poore project ke liye custom exception classes deti hai.
#
# Kyun custom exceptions?
#   1. `except Exception` se better — specific errors catch kar sakte ho
#   2. Clean error messages — user ko meaningful info mile
#   3. Debugging easy — turant pata chale kya fail hua
#   4. Flask me specific HTTP status codes return kar sakein
#
# STRUCTURE:
#   KisanBazaarError (base)
#     ├── DataFetchError
#     │     ├── APIError
#     │     └── CheckpointError
#     ├── DataValidationError
#     ├── DataCleanError
#     ├── DatabaseError
#     ├── ModelError
#     │     ├── ModelNotFoundError
#     │     └── ModelTrainingError
#     ├── PredictionError
#     └── ChatbotError
# ============================================================


# ============================================================
# BASE EXCEPTION
# ============================================================

class KisanBazaarError(Exception):
    """
    Sabhi custom exceptions ka base class.

    Ye ensure karta hai ki hum `except KisanBazaarError:` likh kar
    apne project ke saare errors ek saath catch kar sakein, aur
    unhe third-party errors se distinguish kar sakein.

    Attributes:
        message: Human-readable error description.
        details: Optional dict with additional context (kis file me,
                 kis record pe, etc.) — debugging ke liye.
    """

    def __init__(self, message: str = "", details: dict = None):
        self.message = message
        self.details = details or {}
        super().__init__(self.message)

    def __str__(self):
        if self.details:
            detail_str = ", ".join(f"{k}={v}" for k, v in self.details.items())
            return f"{self.message} | Details: {detail_str}"
        return self.message

    def to_dict(self) -> dict:
        """
        JSON-serializable form return karta hai.
        Flask ke error handler me ye useful hoga.
        """
        return {
            "error": self.__class__.__name__,
            "message": self.message,
            "details": self.details,
        }


# ============================================================
# SECTION 1: DATA FETCH ERRORS
# ============================================================

class DataFetchError(KisanBazaarError):
    """
    Jab Government API se data fetch karne me koi problem aaye.

    Kab raise karenge:
      - API key missing ya invalid
      - Network timeout
      - API ne 5xx error diya
      - Response JSON me convert nahi ho paaya
    """
    pass


class APIError(DataFetchError):
    """
    Specific API-related error (HTTP status, rate limit, etc.).

    Attributes:
        status_code: HTTP status code (agar mile).
    """

    def __init__(self, message: str = "", status_code: int = None, details: dict = None):
        super().__init__(message, details)
        self.status_code = status_code
        if status_code:
            self.details["status_code"] = status_code


class CheckpointError(DataFetchError):
    """
    Checkpoint file load/save me problem.

    Daily fetch me checkpoint track karta hai ki kaunsi date tak
    data successfully fetch hua hai. Agar ye fail ho to issue raise karo.
    """
    pass


# ============================================================
# SECTION 2: DATA VALIDATION & CLEANING ERRORS
# ============================================================

class DataValidationError(KisanBazaarError):
    """
    Jab ek record validate karne me fail ho.

    Kab raise karenge:
      - Arrival_Date invalid format me hai
      - Price negative ya non-numeric hai
      - Required field missing hai

    Note: Aamtaur pe hum invalid records ko skip karke log karte hain,
    pura batch fail nahi karte. Ye exception tab raise karte hain
    jab pura batch hi corrupt lage.
    """
    pass


class DataCleanError(KisanBazaarError):
    """
    Data cleaning me unexpected error.

    Kab raise karenge:
      - Date conversion fail ho gayi
      - Numeric conversion exception aayi
      - Cleaner ka internal logic fail hua
    """
    pass


# ============================================================
# SECTION 3: DATABASE ERRORS
# ============================================================

class DatabaseError(KisanBazaarError):
    """
    SQLite database se related koi bhi error.

    Kab raise karenge:
      - Connection fail
      - Table exist nahi karti
      - Query syntax error
      - Unique constraint violation (jab expected na ho)
      - DB locked hai
    """
    pass


# ============================================================
# SECTION 4: ML MODEL ERRORS
# ============================================================

class ModelError(KisanBazaarError):
    """ML model se related errors ka base class."""
    pass


class ModelNotFoundError(ModelError):
    """
    Jab required trained model file nahi mile.

    Kab raise karenge:
      - `current_model.pkl` exist nahi karta
      - Model path galat hai
      - Joblib load fail hua
    """
    pass


class ModelTrainingError(ModelError):
    """
    Model training pipeline me error.

    Kab raise karenge:
      - Training data insufficient hai
      - Feature engineering fail hui
      - Model converge nahi hua
      - Evaluation me kuch galat hua
    """
    pass


# ============================================================
# SECTION 5: PREDICTION ERRORS
# ============================================================

class PredictionError(KisanBazaarError):
    """
    Prediction pipeline me error.

    Kab raise karenge:
      - Input validation fail
      - Historical data insufficient (lag features nahi ban paaye)
      - Feature generation me problem
      - Model ne exception diya predict karte waqt
    """
    pass


# ============================================================
# SECTION 6: CHATBOT ERRORS
# ============================================================

class ChatbotError(KisanBazaarError):
    """
    AI chatbot se related errors.

    Kab raise karenge:
      - AI API key missing ya invalid
      - LLM API ne error diya
      - Context building fail hui
      - Prompt me problem
    """
    pass


# ============================================================
# SECTION 7: CONFIGURATION ERRORS
# ============================================================

class ConfigurationError(KisanBazaarError):
    """
    Config ya .env me kuch galat hai.

    Kab raise karenge:
      - Required env variable missing
      - API key empty hai
      - Invalid value (jaise negative timeout)
    """
    pass


# ============================================================
# SECTION 8: DIRECT RUN — Quick Test
# ============================================================
if __name__ == "__main__":
    print("=" * 55)
    print("KisanBazaar AI — Custom Exceptions Test")
    print("=" * 55)

    # Test 1: Simple error
    try:
        raise DatabaseError("Table market_prices nahi mili")
    except KisanBazaarError as e:
        print(f"\n✅ Caught: {e}")
        print(f"   As dict: {e.to_dict()}")

    # Test 2: Error with details
    try:
        raise DataValidationError(
            "Invalid date format",
            details={"raw_value": "31/13/2026", "field": "Arrival_Date"},
        )
    except KisanBazaarError as e:
        print(f"\n✅ Caught: {e}")
        print(f"   As dict: {e.to_dict()}")

    # Test 3: APIError with status code
    try:
        raise APIError("Rate limit exceeded", status_code=429)
    except DataFetchError as e:  # Parent class se bhi catch hota hai
        print(f"\n✅ Caught (as DataFetchError): {e}")
        print(f"   Status: {e.status_code}")
        print(f"   As dict: {e.to_dict()}")

    # Test 4: Model error
    try:
        raise ModelNotFoundError(
            "current_model.pkl missing",
            details={"path": "ml/models/current_model.pkl"},
        )
    except ModelError as e:
        print(f"\n✅ Caught (as ModelError): {e}")

    # Test 5: Catch ALL KisanBazaar errors ek saath
    errors = [
        DataFetchError("Network timeout"),
        DataValidationError("Negative price"),
        PredictionError("Insufficient history"),
        ChatbotError("AI API key missing"),
    ]
    print("\n--- Catching all KisanBazaar errors ---")
    for err in errors:
        try:
            raise err
        except KisanBazaarError as e:
            print(f"  ✅ {e.__class__.__name__}: {e.message}")

    print("\n" + "=" * 55)
    print("✅ Exceptions test complete.")