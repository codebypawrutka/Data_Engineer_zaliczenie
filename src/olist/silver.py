"""Krok 2: SILVER — czyszczenie, testy jakości danych, kwarantanna i raport.

Co się dzieje dla każdej tabeli:
1. Czyszczenie: trim, ujednolicenie wielkości liter (miasta małe, stany wielkie),
   usunięcie identycznych duplikatów, poprawki nazw kolumn, wzbogacenie
   (np. angielska nazwa kategorii produktu).
2. Testy jakości: każda reguła to wyrażenie Polars zwracające True dla
   poprawnego wiersza. NULL w wyniku reguły traktujemy jak błąd.
3. Podział: wiersze z co najmniej jednym błędem → data/lake/quarantine/<tabela>
   (z kolumną _failed_rules), poprawne → data/lake/silver/<tabela>.
4. Raport: data/reports/dq_report.json i dq_report.md (+ kopia z datą).
5. Bezpiecznik: jeśli odsetek kwarantanny > MAX_QUARANTINE_PCT → wyjątek.

Kolejność tabel ma znaczenie: testy integralności referencyjnej sprawdzają
klucze względem JUŻ OCZYSZCZONYCH tabel nadrzędnych (np. order_items → orders).
"""
import json
import logging
from datetime import datetime

import polars as pl

from olist.config import BRONZE, MAX_QUARANTINE_PCT, QUARANTINE, REPORTS, SILVER, table_dir

log = logging.getLogger(__name__)

BR_STATES = {
    "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS", "MG", "PA",
    "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC", "SP", "SE", "TO",
}
ORDER_STATUSES = {
    "delivered", "shipped", "canceled", "unavailable", "invoiced",
    "processing", "created", "approved",
}
PAYMENT_TYPES = {"credit_card", "boleto", "voucher", "debit_card", "not_defined"}
# prostokąt obejmujący Brazylię (do odsiewania błędnych współrzędnych)
BR_LAT = (-33.75, 5.27)
BR_LNG = (-73.99, -34.79)


# --------------------------------------------------------------------------- #
# Mini-framework DQ
# --------------------------------------------------------------------------- #
def read_bronze(table: str) -> pl.DataFrame:
    return pl.read_parquet(BRONZE / table / "data.parquet").drop("_ingested_at", "_source_file")


def is_unique(*cols: str) -> pl.Expr:
    """True, gdy klucz nie jest pusty i występuje dokładnie raz."""
    not_null = pl.all_horizontal([pl.col(c).is_not_null() for c in cols])
    key = pl.struct(*cols) if len(cols) > 1 else pl.col(cols[0])
    return not_null & ~key.is_duplicated()


def exists_in(col: str, parent: pl.DataFrame, parent_col: str) -> pl.Expr:
    """Integralność referencyjna: wartość istnieje w tabeli nadrzędnej."""
    return pl.col(col).is_in(parent[parent_col].unique().implode())


def apply_checks(table: str, df: pl.DataFrame, checks: dict[str, pl.Expr], dedup_removed: int):
    flagged = df.with_columns(
        [expr.fill_null(False).alias(f"_ok_{name}") for name, expr in checks.items()]
    )
    ok_cols = [f"_ok_{name}" for name in checks]
    all_ok = pl.all_horizontal(ok_cols)
    flagged = flagged.with_columns(
        pl.concat_list([pl.when(~pl.col(f"_ok_{n}")).then(pl.lit(n)) for n in checks])
        .list.drop_nulls()
        .list.join(",")
        .alias("_failed_rules")
    )

    good = flagged.filter(all_ok).drop(ok_cols + ["_failed_rules"])
    bad = flagged.filter(~all_ok).drop(ok_cols).with_columns(
        pl.lit(datetime.now()).alias("_quarantined_at")
    )

    good.write_parquet(table_dir(SILVER, table) / "data.parquet")
    bad.write_parquet(table_dir(QUARANTINE, table) / "data.parquet")

    rule_fails = {n: int((~flagged[f"_ok_{n}"]).sum()) for n in checks}
    pct = round(100 * bad.height / df.height, 3) if df.height else 0.0
    log.info("silver/%s: %d OK, %d w kwarantannie (%.3f%%)", table, good.height, bad.height, pct)
    return good, {
        "table": table,
        "rows_in": df.height + dedup_removed,
        "exact_duplicates_removed": dedup_removed,
        "rows_ok": good.height,
        "rows_quarantined": bad.height,
        "quarantine_pct": pct,
        "rule_failures": rule_fails,
    }


def dedup(df: pl.DataFrame) -> tuple[pl.DataFrame, int]:
    out = df.unique(maintain_order=True)
    return out, df.height - out.height


def clean_text(*cols: str, case: str) -> list[pl.Expr]:
    exprs = []
    for c in cols:
        e = pl.col(c).str.strip_chars()
        e = e.str.to_lowercase() if case == "lower" else e.str.to_uppercase()
        exprs.append(e.alias(c))
    return exprs


# --------------------------------------------------------------------------- #
# Tabele
# --------------------------------------------------------------------------- #
def build_customers():
    df, d = dedup(read_bronze("customers").with_columns(
        clean_text("customer_city", case="lower") + clean_text("customer_state", case="upper")
    ))
    return apply_checks("customers", df, {
        "customer_pk_unique": is_unique("customer_id"),
        "customer_unique_id_not_null": pl.col("customer_unique_id").is_not_null(),
        "customer_state_valid": pl.col("customer_state").is_in(list(BR_STATES)),
        "customer_zip_5_digits": pl.col("customer_zip_code_prefix").str.contains(r"^\d{5}$"),
    }, d)


def build_sellers():
    df, d = dedup(read_bronze("sellers").with_columns(
        clean_text("seller_city", case="lower") + clean_text("seller_state", case="upper")
    ))
    return apply_checks("sellers", df, {
        "seller_pk_unique": is_unique("seller_id"),
        "seller_state_valid": pl.col("seller_state").is_in(list(BR_STATES)),
        "seller_zip_5_digits": pl.col("seller_zip_code_prefix").str.contains(r"^\d{5}$"),
    }, d)


def build_category_translation():
    df, d = dedup(read_bronze("category_translation").with_columns(
        clean_text("product_category_name", "product_category_name_english", case="lower")
    ))
    return apply_checks("category_translation", df, {
        "category_pk_unique": is_unique("product_category_name"),
        "category_english_not_null": pl.col("product_category_name_english").is_not_null(),
    }, d)


def build_products(translation: pl.DataFrame):
    df = (
        read_bronze("products")
        .rename({
            "product_name_lenght": "product_name_length",
            "product_description_lenght": "product_description_length",
        })
        .with_columns(clean_text("product_category_name", case="lower"))
        .join(translation.select("product_category_name", "product_category_name_english"),
              on="product_category_name", how="left")
    )
    df, d = dedup(df)
    dims = ["product_weight_g", "product_length_cm", "product_height_cm", "product_width_cm"]
    return apply_checks("products", df, {
        "product_pk_unique": is_unique("product_id"),
        # brak kategorii jest dozwolony (w wymiarze → 'unknown'), ale ujemne wymiary nie
        "product_dimensions_non_negative": pl.all_horizontal(
            [pl.col(c).is_null() | (pl.col(c) >= 0) for c in dims]
        ),
    }, d)


def build_orders(customers: pl.DataFrame):
    df, d = dedup(read_bronze("orders").with_columns(clean_text("order_status", case="lower")))
    delivered = pl.col("order_delivered_customer_date")
    purchased = pl.col("order_purchase_timestamp")
    return apply_checks("orders", df, {
        "order_pk_unique": is_unique("order_id"),
        "order_status_valid": pl.col("order_status").is_in(list(ORDER_STATUSES)),
        "order_purchase_ts_not_null": purchased.is_not_null(),
        "order_fk_customer": exists_in("customer_id", customers, "customer_id"),
        "order_delivered_after_purchase": delivered.is_null() | (delivered >= purchased),
        "order_delivered_has_date": (pl.col("order_status") != "delivered") | delivered.is_not_null(),
    }, d)


def build_order_items(orders, products, sellers):
    df, d = dedup(read_bronze("order_items"))
    return apply_checks("order_items", df, {
        "item_pk_unique": is_unique("order_id", "order_item_id"),
        "item_price_positive": (pl.col("price") > 0) & (pl.col("freight_value") >= 0),
        "item_fk_order": exists_in("order_id", orders, "order_id"),
        "item_fk_product": exists_in("product_id", products, "product_id"),
        "item_fk_seller": exists_in("seller_id", sellers, "seller_id"),
    }, d)


def build_order_payments(orders):
    df, d = dedup(read_bronze("order_payments").with_columns(
        clean_text("payment_type", case="lower")
    ))
    return apply_checks("order_payments", df, {
        "payment_pk_unique": is_unique("order_id", "payment_sequential"),
        "payment_type_valid": pl.col("payment_type").is_in(list(PAYMENT_TYPES)),
        "payment_value_non_negative": pl.col("payment_value") >= 0,
        "payment_installments_positive": pl.col("payment_installments") >= 1,
        "payment_fk_order": exists_in("order_id", orders, "order_id"),
    }, d)


def build_order_reviews(orders):
    df, d = dedup(read_bronze("order_reviews"))
    return apply_checks("order_reviews", df, {
        "review_pk_unique": is_unique("review_id", "order_id"),
        "review_score_1_5": pl.col("review_score").is_between(1, 5),
        "review_fk_order": exists_in("order_id", orders, "order_id"),
    }, d)


def build_geolocation():
    """Geolokalizacja ma wiele punktów na jeden prefiks kodu → po testach agregujemy."""
    df, d = dedup(read_bronze("geolocation").with_columns(
        clean_text("geolocation_city", case="lower") + clean_text("geolocation_state", case="upper")
    ))
    good, stats = apply_checks("geolocation", df, {
        "geo_zip_5_digits": pl.col("geolocation_zip_code_prefix").str.contains(r"^\d{5}$"),
        "geo_lat_in_brazil": pl.col("geolocation_lat").is_between(*BR_LAT),
        "geo_lng_in_brazil": pl.col("geolocation_lng").is_between(*BR_LNG),
        "geo_state_valid": pl.col("geolocation_state").is_in(list(BR_STATES)),
    }, d)
    agg = good.group_by("geolocation_zip_code_prefix").agg(
        pl.col("geolocation_lat").mean(),
        pl.col("geolocation_lng").mean(),
        pl.col("geolocation_city").mode().first(),
        pl.col("geolocation_state").mode().first(),
        pl.len().alias("points"),
    ).sort("geolocation_zip_code_prefix")
    agg.write_parquet(table_dir(SILVER, "geolocation") / "data.parquet")
    stats["rows_after_aggregation"] = agg.height
    return agg, stats


# --------------------------------------------------------------------------- #
# Raport
# --------------------------------------------------------------------------- #
def write_report(stats: list[dict]) -> None:
    REPORTS.mkdir(parents=True, exist_ok=True)
    ts = datetime.now()
    payload = {"generated_at": ts.isoformat(timespec="seconds"),
               "max_quarantine_pct": MAX_QUARANTINE_PCT, "tables": stats}
    js = json.dumps(payload, indent=2, ensure_ascii=False)
    (REPORTS / "dq_report.json").write_text(js, encoding="utf-8")
    (REPORTS / f"dq_report_{ts:%Y%m%d_%H%M%S}.json").write_text(js, encoding="utf-8")

    lines = [
        "# Raport jakości danych (warstwa silver)",
        "",
        f"Wygenerowano: {payload['generated_at']}  ",
        f"Próg kwarantanny: {MAX_QUARANTINE_PCT}%",
        "",
        "## Podsumowanie tabel",
        "",
        "| Tabela | Wiersze wej. | Duplikaty usunięte | OK | Kwarantanna | % kwarantanny |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for s in stats:
        lines.append(f"| {s['table']} | {s['rows_in']:,} | {s['exact_duplicates_removed']:,} | "
                     f"{s['rows_ok']:,} | {s['rows_quarantined']:,} | {s['quarantine_pct']} |")
    lines += ["", "## Wyniki testów", "", "| Tabela | Test | Liczba błędów | Status |", "|---|---|---:|---|"]
    n_tests = 0
    for s in stats:
        for rule, fails in s["rule_failures"].items():
            n_tests += 1
            lines.append(f"| {s['table']} | `{rule}` | {fails:,} | {'PASS' if fails == 0 else 'FAIL → kwarantanna'} |")
    lines += ["", f"Łącznie testów: **{n_tests}**. Błędne wiersze: `data/lake/quarantine/<tabela>/` "
              "(kolumna `_failed_rules` mówi, które reguły nie przeszły)."]
    (REPORTS / "dq_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def run() -> dict:
    stats = []
    translation, s = build_category_translation(); stats.append(s)
    customers, s = build_customers(); stats.append(s)
    sellers, s = build_sellers(); stats.append(s)
    products, s = build_products(translation); stats.append(s)
    orders, s = build_orders(customers); stats.append(s)
    _, s = build_order_items(orders, products, sellers); stats.append(s)
    _, s = build_order_payments(orders); stats.append(s)
    _, s = build_order_reviews(orders); stats.append(s)
    _, s = build_geolocation(); stats.append(s)

    write_report(stats)

    breached = [f"{s['table']} ({s['quarantine_pct']}%)" for s in stats
                if s["quarantine_pct"] > MAX_QUARANTINE_PCT]
    if breached:
        raise ValueError(f"Przekroczony próg kwarantanny {MAX_QUARANTINE_PCT}%: {', '.join(breached)}. "
                         "Sprawdź data/reports/dq_report.md")
    return {s["table"]: {"ok": s["rows_ok"], "quarantined": s["rows_quarantined"]} for s in stats}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(json.dumps(run(), indent=2))
