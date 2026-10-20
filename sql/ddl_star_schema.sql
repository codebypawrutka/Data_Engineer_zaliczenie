-- =====================================================================
-- Model gwiazdy w hurtowni (PostgreSQL)
-- Ziarno faktu: jeden wiersz = jedna pozycja zamówienia (order_id, order_item_id)
-- Klucze surogatowe (*_key) nadaje potok w Pythonie, deterministycznie
-- (sortowanie po kluczu naturalnym), bo każde uruchomienie to pełne przeładowanie.
-- =====================================================================

CREATE TABLE IF NOT EXISTS dim_date (
    date_key      INTEGER PRIMARY KEY,          -- np. 20171124
    full_date     DATE    NOT NULL UNIQUE,
    year          SMALLINT NOT NULL,
    quarter       SMALLINT NOT NULL,
    month         SMALLINT NOT NULL,
    month_name    TEXT     NOT NULL,
    year_month    CHAR(7)  NOT NULL,             -- '2017-11'
    day           SMALLINT NOT NULL,
    day_of_week   SMALLINT NOT NULL,             -- 1 = poniedziałek
    day_name      TEXT     NOT NULL,
    is_weekend    BOOLEAN  NOT NULL
);

CREATE TABLE IF NOT EXISTS dim_customer (
    customer_key        INTEGER PRIMARY KEY,
    customer_id         TEXT NOT NULL UNIQUE,    -- w Olist: id klienta PER ZAMÓWIENIE
    customer_unique_id  TEXT NOT NULL,           -- prawdziwy klient → używać do retencji
    zip_code_prefix     TEXT,
    city                TEXT,
    state               CHAR(2),
    lat                 DOUBLE PRECISION,
    lng                 DOUBLE PRECISION
);
CREATE INDEX IF NOT EXISTS ix_dim_customer_unique ON dim_customer (customer_unique_id);

CREATE TABLE IF NOT EXISTS dim_seller (
    seller_key       INTEGER PRIMARY KEY,
    seller_id        TEXT NOT NULL UNIQUE,
    zip_code_prefix  TEXT,
    city             TEXT,
    state            CHAR(2),
    lat              DOUBLE PRECISION,
    lng              DOUBLE PRECISION
);

CREATE TABLE IF NOT EXISTS dim_product (
    product_key        INTEGER PRIMARY KEY,
    product_id         TEXT NOT NULL UNIQUE,
    category_name_pt   TEXT,
    category_name_en   TEXT NOT NULL,           -- 'unknown', gdy brak kategorii
    photos_qty         INTEGER,
    weight_g           INTEGER,
    length_cm          INTEGER,
    height_cm          INTEGER,
    width_cm           INTEGER
);

CREATE TABLE IF NOT EXISTS fact_order_items (
    order_id            TEXT     NOT NULL,
    order_item_id       INTEGER  NOT NULL,
    customer_key        INTEGER  NOT NULL REFERENCES dim_customer (customer_key),
    seller_key          INTEGER  NOT NULL REFERENCES dim_seller (seller_key),
    product_key         INTEGER  NOT NULL REFERENCES dim_product (product_key),
    date_key            INTEGER  NOT NULL REFERENCES dim_date (date_key),   -- data zakupu
    delivered_date_key  INTEGER  REFERENCES dim_date (date_key),            -- data doręczenia
    order_status        TEXT     NOT NULL,
    price               NUMERIC(10, 2) NOT NULL,
    freight_value       NUMERIC(10, 2) NOT NULL,
    delivery_days       INTEGER,            -- doręczenie - zakup (dni), NULL gdy niedoręczone
    is_late             BOOLEAN,            -- doręczone po szacowanym terminie
    PRIMARY KEY (order_id, order_item_id)
);
CREATE INDEX IF NOT EXISTS ix_fact_date     ON fact_order_items (date_key);
CREATE INDEX IF NOT EXISTS ix_fact_customer ON fact_order_items (customer_key);
CREATE INDEX IF NOT EXISTS ix_fact_seller   ON fact_order_items (seller_key);
CREATE INDEX IF NOT EXISTS ix_fact_product  ON fact_order_items (product_key);

COMMENT ON TABLE fact_order_items IS
  'Fakt sprzedaży; ziarno = pozycja zamówienia. Płatności są per zamówienie, więc celowo ich tu nie ma (dublowanie kwot).';
