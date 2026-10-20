"""Krok 3: ładowanie modelu gwiazdy z warstwy silver do PostgreSQL.

Co się dzieje:
1. Tworzymy tabele (sql/ddl_star_schema.sql, CREATE ... IF NOT EXISTS).
2. Budujemy wymiary w Polars i nadajemy klucze surogatowe (1..N po kluczu naturalnym).
3. Budujemy fakt: order_items + orders + mapowanie kluczy naturalnych na surogatowe.
4. W JEDNEJ transakcji: TRUNCATE wszystkich tabel + COPY nowych danych.
   Jeśli coś się nie uda — rollback, w hurtowni zostają poprzednie dane.
   Pełne przeładowanie = każde uruchomienie daje ten sam wynik (idempotencja).
"""
import io
import logging
from datetime import date

import polars as pl
import psycopg2

from olist.config import DWH_URL, SILVER, SQL_DIR

log = logging.getLogger(__name__)

LOAD_ORDER = ["dim_date", "dim_customer", "dim_seller", "dim_product", "fact_order_items"]


def silver(table: str) -> pl.DataFrame:
    return pl.read_parquet(SILVER / table / "data.parquet")


def with_key(df: pl.DataFrame, natural_key: str, key_name: str) -> pl.DataFrame:
    return df.sort(natural_key).with_row_index(key_name, offset=1).with_columns(
        pl.col(key_name).cast(pl.Int32)
    )


def build_dim_date(start: date, end: date) -> pl.DataFrame:
    d = pl.date_range(start, end, "1d", eager=True).alias("full_date").to_frame()
    return d.with_columns(
        pl.col("full_date").dt.strftime("%Y%m%d").cast(pl.Int32).alias("date_key"),
        pl.col("full_date").dt.year().alias("year"),
        pl.col("full_date").dt.quarter().alias("quarter"),
        pl.col("full_date").dt.month().alias("month"),
        pl.col("full_date").dt.strftime("%B").alias("month_name"),
        pl.col("full_date").dt.strftime("%Y-%m").alias("year_month"),
        pl.col("full_date").dt.day().alias("day"),
        pl.col("full_date").dt.weekday().alias("day_of_week"),
        pl.col("full_date").dt.strftime("%A").alias("day_name"),
        (pl.col("full_date").dt.weekday() >= 6).alias("is_weekend"),
    ).select("date_key", "full_date", "year", "quarter", "month", "month_name",
             "year_month", "day", "day_of_week", "day_name", "is_weekend")


def build_model() -> dict[str, pl.DataFrame]:
    geo = silver("geolocation").select(
        pl.col("geolocation_zip_code_prefix").alias("zip_code_prefix"),
        pl.col("geolocation_lat").alias("lat"),
        pl.col("geolocation_lng").alias("lng"),
    )

    dim_customer = with_key(
        silver("customers").rename({
            "customer_zip_code_prefix": "zip_code_prefix",
            "customer_city": "city", "customer_state": "state",
        }).join(geo, on="zip_code_prefix", how="left"),
        "customer_id", "customer_key",
    ).select("customer_key", "customer_id", "customer_unique_id",
             "zip_code_prefix", "city", "state", "lat", "lng")

    dim_seller = with_key(
        silver("sellers").rename({
            "seller_zip_code_prefix": "zip_code_prefix",
            "seller_city": "city", "seller_state": "state",
        }).join(geo, on="zip_code_prefix", how="left"),
        "seller_id", "seller_key",
    ).select("seller_key", "seller_id", "zip_code_prefix", "city", "state", "lat", "lng")

    dim_product = with_key(silver("products"), "product_id", "product_key").select(
        "product_key", "product_id",
        pl.col("product_category_name").alias("category_name_pt"),
        pl.col("product_category_name_english").fill_null(
            pl.col("product_category_name")).fill_null("unknown").alias("category_name_en"),
        pl.col("product_photos_qty").alias("photos_qty"),
        pl.col("product_weight_g").alias("weight_g"),
        pl.col("product_length_cm").alias("length_cm"),
        pl.col("product_height_cm").alias("height_cm"),
        pl.col("product_width_cm").alias("width_cm"),
    )

    orders = silver("orders")
    purchased = pl.col("order_purchase_timestamp")
    delivered = pl.col("order_delivered_customer_date")
    fact = (
        silver("order_items")
        .join(orders, on="order_id", how="inner")
        .join(dim_customer.select("customer_id", "customer_key"), on="customer_id", how="inner")
        .join(dim_seller.select("seller_id", "seller_key"), on="seller_id", how="inner")
        .join(dim_product.select("product_id", "product_key"), on="product_id", how="inner")
        .select(
            "order_id", "order_item_id", "customer_key", "seller_key", "product_key",
            purchased.dt.strftime("%Y%m%d").cast(pl.Int32).alias("date_key"),
            delivered.dt.strftime("%Y%m%d").cast(pl.Int32).alias("delivered_date_key"),
            "order_status",
            pl.col("price").round(2),
            pl.col("freight_value").round(2),
            (delivered.dt.date() - purchased.dt.date()).dt.total_days().cast(pl.Int32).alias("delivery_days"),
            pl.when(delivered.is_null()).then(None)
              .otherwise(delivered.dt.date() > pl.col("order_estimated_delivery_date").dt.date())
              .alias("is_late"),
        )
        .sort("order_id", "order_item_id")
    )

    all_dates = pl.concat([
        orders.select(purchased.dt.date().alias("d")),
        orders.select(delivered.dt.date().alias("d")),
    ]).drop_nulls()
    dim_date = build_dim_date(all_dates["d"].min(), all_dates["d"].max())

    return {"dim_date": dim_date, "dim_customer": dim_customer, "dim_seller": dim_seller,
            "dim_product": dim_product, "fact_order_items": fact}


def copy_df(cur, table: str, df: pl.DataFrame) -> None:
    """Szybkie ładowanie przez COPY FROM STDIN (CSV w pamięci)."""
    buf = io.StringIO()
    df.write_csv(buf, include_header=False, null_value="", datetime_format="%Y-%m-%d %H:%M:%S")
    buf.seek(0)
    cols = ", ".join(df.columns)
    cur.copy_expert(f"COPY {table} ({cols}) FROM STDIN WITH (FORMAT csv, NULL '')", buf)


def run() -> dict:
    model = build_model()
    ddl = (SQL_DIR / "ddl_star_schema.sql").read_text(encoding="utf-8")

    conn = psycopg2.connect(DWH_URL)
    try:
        with conn:  # jedna transakcja: commit na końcu albo rollback przy błędzie
            with conn.cursor() as cur:
                cur.execute(ddl)
                cur.execute("TRUNCATE " + ", ".join(reversed(LOAD_ORDER)))
                for table in LOAD_ORDER:
                    copy_df(cur, table, model[table])
                    log.info("%s: %d wierszy", table, model[table].height)
                cur.execute("ANALYZE")  # świeże statystyki dla planisty zapytań
    finally:
        conn.close()

    return {t: model[t].height for t in LOAD_ORDER}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(run())
