-- ============================================================
-- KisanBazaar AI — SQLite Database Schema
-- ============================================================
-- Ye file database ki saari tables aur indexes define karti hai.
-- Ise run karne ke liye: database/db.py me init_db() call hoti hai.
--
-- Tables:
--   1. market_prices      → Government mandi ka daily price data (MAIN)
--   2. data_sync_logs     → Daily API fetch ka record (debugging)
--   3. model_versions     → ML model ki versioning
--   4. prediction_logs    → Har prediction ka record
--
-- IMPORTANT RULES (SRS ke hisaab se):
--   - Arrival_Date ko TEXT me "YYYY-MM-DD" format me store karna hai.
--     SQLite me DATE datatype nahi hota, TEXT use karte hain jo
--     lexicographic sort me bhi date jaisa hi kaam karta hai.
--   - Sirf latest 2 years ka data rakhenge (rolling retention).
--   - market_prices table ko BOTH Dashboard aur ML dono use karenge.
--     Koi separate table nahi banegi.
--   - Daily update idempotent hona chahiye (duplicate rows nahi banne chahiye).
-- ============================================================


-- ============================================================
-- TABLE 1: market_prices
-- ============================================================
-- Ye sabse important table hai. Government API aur Historical CSV
-- dono ka data yahan aayega.
--
-- Fields:
--   id            → Auto-increment primary key
--   state         → State name (e.g., "Uttar Pradesh")
--   district      → District name (e.g., "Kanpur Nagar")
--   market        → Mandi/Market name (e.g., "Kanpur")
--   commodity     → Commodity name (e.g., "Potato")
--   variety       → Variety name (e.g., "Jyoti")
--   grade         → Grade (e.g., "FAQ", "Non-FAQ")
--   arrival_date  → Date in YYYY-MM-DD format (TEXT)
--   min_price     → Minimum price (numeric)
--   max_price     → Maximum price (numeric)
--   modal_price   → Modal price (numeric) — ye ML ka TARGET hai
--   source        → Data kahan se aaya: "government_api" ya "historical_csv"
--   fetched_at    → Kab fetch hua (timestamp)
--   created_at    → Kab row insert hui (timestamp)
-- ============================================================

CREATE TABLE IF NOT EXISTS market_prices (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Location info
    state           TEXT NOT NULL,
    district        TEXT,
    market          TEXT NOT NULL,

    -- Commodity info
    commodity       TEXT NOT NULL,
    variety         TEXT,
    grade           TEXT,

    -- Date (stored as YYYY-MM-DD TEXT for SQLite compatibility)
    arrival_date    TEXT NOT NULL,

    -- Prices (REAL = floating point number)
    min_price       REAL,
    max_price       REAL,
    modal_price     REAL,

    -- Metadata (debugging ke liye useful)
    source          TEXT NOT NULL DEFAULT 'government_api',
    fetched_at      TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at      TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- --------------------------------------------------------
    -- UNIQUE CONSTRAINT (Duplicate prevention)
    -- --------------------------------------------------------
    -- Ye combination unique hona chahiye. Agar API same record
    -- dobara bhejta hai, to INSERT OR IGNORE / INSERT OR REPLACE
    -- se duplicate nahi banega.
    --
    -- NOTE: Grade ko include kiya hai kyunki SRS me bola gaya hai
    -- ki Market + Commodity + Variety + Date always unique nahi hota.
    -- Actual API data inspect hone ke baad, agar zaroorat pade to
    -- hum is unique key ko tweak kar sakte hain.
    UNIQUE (state, district, market, commodity, variety, grade, arrival_date)
);


-- ------------------------------------------------------------
-- INDEXES for market_prices
-- ------------------------------------------------------------
-- Dashboard filters fast chalane ke liye. Bina indexes ke
-- lakhs of rows me query slow ho jayegi.

-- Index 1: Date range queries (Dashboard trend charts)
CREATE INDEX IF NOT EXISTS idx_market_prices_arrival_date
    ON market_prices (arrival_date);

-- Index 2: State-wise filtering
CREATE INDEX IF NOT EXISTS idx_market_prices_state
    ON market_prices (state);

-- Index 3: District-wise filtering
CREATE INDEX IF NOT EXISTS idx_market_prices_district
    ON market_prices (district);

-- Index 4: Market-wise filtering (dashboard ka main filter)
CREATE INDEX IF NOT EXISTS idx_market_prices_market
    ON market_prices (market);

-- Index 5: Commodity-wise filtering
CREATE INDEX IF NOT EXISTS idx_market_prices_commodity
    ON market_prices (commodity);

-- Index 6: Variety-wise filtering
CREATE INDEX IF NOT EXISTS idx_market_prices_variety
    ON market_prices (variety);

-- Index 7: Composite index (dashboard ka sabse common query)
-- Ye market + commodity + variety + date ko ek saath filter karta hai.
CREATE INDEX IF NOT EXISTS idx_market_prices_composite
    ON market_prices (market, commodity, variety, arrival_date);


-- ============================================================
-- TABLE 2: data_sync_logs
-- ============================================================
-- Har daily API fetch ka record rakhta hai.
-- Debugging ke liye useful: "Aaj sync chala ya nahi? Kitne records aaye?
-- Kitne duplicates mile? Koi error aaya?"
--
-- Fields:
--   id                 → Auto-increment
--   sync_date          → Kis date ka data fetch kiya (YYYY-MM-DD)
--   started_at         → Sync kab shuru hua
--   completed_at       → Sync kab khatam hua
--   records_fetched    → API se total kitne records aaye
--   records_inserted   → SQLite me kitne insert hue (new)
--   records_updated    → Kitne update hue (agar same record mila)
--   duplicates         → Kitne duplicate the
--   errors             → Kitne records invalid the
--   status             → 'SUCCESS', 'PARTIAL', 'FAILED', 'RUNNING'
--   error_message      → Agar fail hua to reason
-- ============================================================

CREATE TABLE IF NOT EXISTS data_sync_logs (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Kis date ka data fetch hua (YYYY-MM-DD)
    sync_date           TEXT NOT NULL,

    -- Timing info
    started_at          TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at        TEXT,

    -- Counts
    records_fetched     INTEGER DEFAULT 0,
    records_inserted    INTEGER DEFAULT 0,
    records_updated     INTEGER DEFAULT 0,
    duplicates          INTEGER DEFAULT 0,
    errors              INTEGER DEFAULT 0,

    -- Status
    status              TEXT NOT NULL DEFAULT 'RUNNING',
    error_message       TEXT
);

-- Index: Latest sync check karne ke liye
CREATE INDEX IF NOT EXISTS idx_data_sync_logs_sync_date
    ON data_sync_logs (sync_date);

CREATE INDEX IF NOT EXISTS idx_data_sync_logs_status
    ON data_sync_logs (status);


-- ============================================================
-- TABLE 3: model_versions
-- ============================================================
-- ML model ki versioning. Har baar jab model train hota hai,
-- uski entry yahan hoti hai. Ye pata rakhta hai ki kaunsa
-- model currently ACTIVE hai aur kaunsa RETIRED.
--
-- Fields:
--   id                    → Auto-increment
--   version               → Version name (e.g., "v1", "v2", "v3")
--   model_name            → Algorithm name (e.g., "XGBoost", "LightGBM")
--   trained_at            → Kab train hua
--   training_start_date   → Training data ka start date
--   training_end_date     → Training data ka end date
--   mae                   → Mean Absolute Error
--   rmse                  → Root Mean Squared Error
--   mape                  → Mean Absolute Percentage Error
--   status                → 'active', 'archived', 'rejected'
--   model_path            → .pkl file ka path
-- ============================================================

CREATE TABLE IF NOT EXISTS model_versions (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,

    version               TEXT NOT NULL UNIQUE,
    model_name            TEXT NOT NULL,

    -- Training timing
    trained_at            TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    training_start_date   TEXT,
    training_end_date     TEXT,

    -- Evaluation metrics
    mae                   REAL,
    rmse                  REAL,
    mape                  REAL,

    -- Status: 'active', 'archived', 'rejected'
    status                TEXT NOT NULL DEFAULT 'active',

    -- Model file location
    model_path            TEXT
);

CREATE INDEX IF NOT EXISTS idx_model_versions_status
    ON model_versions (status);


-- ============================================================
-- TABLE 4: prediction_logs
-- ============================================================
-- Har user prediction ka record. Future me prediction vs actual
-- compare karne ke liye useful hoga (model monitoring).
--
-- Fields:
--   id               → Auto-increment
--   session_id       → User/session identifier (optional)
--   state            → State
--   district         → District
--   market           → Mandi
--   commodity        → Commodity
--   variety          → Variety
--   requested_date   → Kis date ka prediction maanga
--   predicted_price  → Model ne kya predict kiya
--   model_version    → Kaunsa model use hua
--   quantity_kg      → User ne kitni quantity daali
--   expected_value   → Quantity × predicted price
--   actual_price     → Baad me actual price (agar mila to)
--   prediction_error → actual - predicted
--   created_at       → Kab predict hua
-- ============================================================

CREATE TABLE IF NOT EXISTS prediction_logs (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,

    session_id       TEXT,

    -- Input context
    state            TEXT,
    district         TEXT,
    market           TEXT NOT NULL,
    commodity        TEXT NOT NULL,
    variety          TEXT,
    requested_date   TEXT NOT NULL,

    -- Prediction output
    predicted_price  REAL,
    model_version    TEXT,
    quantity_kg      REAL,
    expected_value   REAL,

    -- Feedback loop (future)
    actual_price     REAL,
    prediction_error REAL,

    created_at       TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_prediction_logs_market_commodity
    ON prediction_logs (market, commodity);

CREATE INDEX IF NOT EXISTS idx_prediction_logs_requested_date
    ON prediction_logs (requested_date);


-- ============================================================
-- END OF SCHEMA
-- ============================================================
-- Ab db.py me init_db() function is file ko read karke execute karega.
-- Uske baad ye saari tables database/kisanbazaar.db me ban jayengi.
-- ============================================================