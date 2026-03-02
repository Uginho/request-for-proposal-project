CREATE TABLE IF NOT EXISTS dishes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL UNIQUE,
    category    TEXT,
    description TEXT,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS ingredients (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL UNIQUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS ingredient_pricing (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    ingredient_id   INTEGER NOT NULL,
    commodity       TEXT,
    price_per_lb    REAL,
    original_price  REAL,
    original_unit   TEXT,
    market          TEXT,
    report_title    TEXT,
    report_date     TEXT,
    source          TEXT DEFAULT 'USDA AMS Market News',
    no_data_reason  TEXT,
    date_fetched    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (ingredient_id) REFERENCES ingredients(id)
);

CREATE TABLE IF NOT EXISTS distributors (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL UNIQUE,
    specialty  TEXT,
    address    TEXT,
    city       TEXT,
    state      TEXT,
    phone      TEXT,
    email      TEXT,
    website    TEXT,
    notes      TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS rfp_emails (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    distributor_id INTEGER NOT NULL,
    to_email       TEXT NOT NULL,
    subject        TEXT,
    body           TEXT,
    status         TEXT DEFAULT 'pending',
    sent_at        TIMESTAMP,
    FOREIGN KEY (distributor_id) REFERENCES distributors(id)
);

CREATE TABLE IF NOT EXISTS dish_ingredients (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    dish_id       INTEGER NOT NULL,
    ingredient_id INTEGER NOT NULL,
    quantity      REAL,
    unit          TEXT,
    notes         TEXT,
    FOREIGN KEY (dish_id)       REFERENCES dishes(id),
    FOREIGN KEY (ingredient_id) REFERENCES ingredients(id)
);
