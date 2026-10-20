"""Krok 1: BRONZE — ingest CSV → Parquet z jawnie zdefiniowanymi typami (Polars).

Co się dzieje:
1. Każdy CSV czytamy w całości jako tekst (infer_schema=False), żeby Polars
   niczego nie "zgadywał" (np. kod pocztowy "01151" nie zamieni się w liczbę 1151).
2. Każdą kolumnę rzutujemy na typ zapisany ręcznie w SCHEMAS.
   strict=False → wartość, której nie da się zrzutować, staje się NULL zamiast
   przerywać ingest. Liczbę takich przypadków logujemy (cast_failures), a złe
   wiersze wyłapią testy jakości w warstwie silver.
3. Dodajemy kolumny techniczne _ingested_at i _source_file (lineage).
4. Zapisujemy data/lake/bronze/<tabela>/data.parquet (nadpisanie = idempotencja).
"""
import json
import logging
from datetime import datetime, timezone

import polars as pl

from olist.config import BRONZE, RAW, REPORTS, table_dir

log = logging.getLogger(__name__)

TS_FORMAT = "%Y-%m-%d %H:%M:%S"
DT = "datetime"  # znacznik typu: parsowanie tekstu wg TS_FORMAT

# tabela -> (plik CSV, {kolumna: typ})
SCHEMAS: dict[str, tuple[str, dict]] = {
    "customers": ("olist_customers_dataset.csv", {
        "customer_id": pl.Utf8,
        "customer_unique_id": pl.Utf8,
        "customer_zip_code_prefix": pl.Utf8,  # tekst! zera wiodące
        "customer_city": pl.Utf8,
        "customer_state": pl.Utf8,
    }),
    "geolocation": ("olist_geolocation_dataset.csv", {
        "geolocation_zip_code_prefix": pl.Utf8,
        "geolocation_lat": pl.Float64,
        "geolocation_lng": pl.Float64,
        "geolocation_city": pl.Utf8,
        "geolocation_state": pl.Utf8,
    }),
    "orders": ("olist_orders_dataset.csv", {
        "order_id": pl.Utf8,
        "customer_id": pl.Utf8,
        "order_status": pl.Utf8,
        "order_purchase_timestamp": DT,
        "order_approved_at": DT,
        "order_delivered_carrier_date": DT,
        "order_delivered_customer_date": DT,
        "order_estimated_delivery_date": DT,
    }),
    "order_items": ("olist_order_items_dataset.csv", {
        "order_id": pl.Utf8,
        "order_item_id": pl.Int32,
        "product_id": pl.Utf8,
        "seller_id": pl.Utf8,
        "shipping_limit_date": DT,
        "price": pl.Float64,
        "freight_value": pl.Float64,
    }),
    "order_payments": ("olist_order_payments_dataset.csv", {
        "order_id": pl.Utf8,
        "payment_sequential": pl.Int32,
        "payment_type": pl.Utf8,
        "payment_installments": pl.Int32,
        "payment_value": pl.Float64,
    }),
    "order_reviews": ("olist_order_reviews_dataset.csv", {
        "review_id": pl.Utf8,
        "order_id": pl.Utf8,
        "review_score": pl.Int8,
        "review_comment_title": pl.Utf8,
        "review_comment_message": pl.Utf8,
        "review_creation_date": DT,
        "review_answer_timestamp": DT,
    }),
    "products": ("olist_products_dataset.csv", {
        "product_id": pl.Utf8,
        "product_category_name": pl.Utf8,
        "product_name_lenght": pl.Int32,         # literówka w oryginale — poprawiamy w silver
        "product_description_lenght": pl.Int32,
        "product_photos_qty": pl.Int32,
        "product_weight_g": pl.Int32,
        "product_length_cm": pl.Int32,
        "product_height_cm": pl.Int32,
        "product_width_cm": pl.Int32,
    }),
    "sellers": ("olist_sellers_dataset.csv", {
        "seller_id": pl.Utf8,
        "seller_zip_code_prefix": pl.Utf8,
        "seller_city": pl.Utf8,
        "seller_state": pl.Utf8,
    }),
    "category_translation": ("product_category_name_translation.csv", {
        "product_category_name": pl.Utf8,
        "product_category_name_english": pl.Utf8,
    }),
}


def _cast_expr(col: str, dtype) -> pl.Expr:
    c = pl.col(col).str.strip_chars()
    if dtype == DT:
        return c.str.to_datetime(TS_FORMAT, strict=False).alias(col)
    if dtype in (pl.Int8, pl.Int16, pl.Int32, pl.Int64):
        # przez Float64, żeby "40.0" też dało się zrzutować na 40
        return c.cast(pl.Float64, strict=False).cast(dtype, strict=False).alias(col)
    return c.cast(dtype, strict=False).alias(col)


def load_table(name: str, file: str, schema: dict) -> dict:
    path = RAW / file
    raw = pl.read_csv(path, infer_schema=False, encoding="utf8-lossy")
    # niektóre pliki Olist mają BOM w nagłówku — usuwamy go z nazw kolumn
    raw = raw.rename({c: c.lstrip("﻿").strip() for c in raw.columns})

    missing = set(schema) - set(raw.columns)
    if missing:
        raise ValueError(f"{file}: brak kolumn {missing}")

    typed = raw.select([_cast_expr(c, t) for c, t in schema.items()])

    # ile niepustych wartości "zginęło" przy rzutowaniu (tylko kolumny nietekstowe)
    cast_failures = {}
    for col, dtype in schema.items():
        if dtype is pl.Utf8:
            continue
        lost = raw.select(
            (pl.col(col).str.strip_chars().str.len_chars() > 0) & typed[col].is_null()
        ).to_series().sum()
        if lost:
            cast_failures[col] = int(lost)
            log.warning("%s.%s: %d wartości nie dało się zrzutować → NULL", name, col, lost)

    typed = typed.with_columns(
        pl.lit(datetime.now(timezone.utc).replace(tzinfo=None)).alias("_ingested_at"),
        pl.lit(file).alias("_source_file"),
    )
    typed.write_parquet(table_dir(BRONZE, name) / "data.parquet")
    log.info("bronze/%s: %d wierszy", name, typed.height)
    return {"table": name, "rows": typed.height, "cast_failures": cast_failures}


def run() -> list[dict]:
    results = [load_table(n, f, s) for n, (f, s) in SCHEMAS.items()]
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / "bronze_ingest.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    for r in run():
        print(r)
