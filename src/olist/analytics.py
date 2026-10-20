"""Krok 4: uruchomienie 5 zapytań analitycznych na hurtowni.

Co się dzieje: każdy plik sql/analytics/*.sql jest wykonywany na Postgresie,
wynik trafia do data/reports/analytics/<nazwa>.csv, a dodatkowo powstaje
data/reports/analytics/summary.md z kilkoma pierwszymi wierszami każdego
wyniku — punkt wyjścia do napisania analizy w docs/analysis.md.
"""
import logging

import polars as pl
import psycopg2

from olist.config import DWH_URL, REPORTS, SQL_DIR

log = logging.getLogger(__name__)


def run_query(conn, sql: str) -> pl.DataFrame:
    with conn.cursor() as cur:
        cur.execute(sql)
        cols = [d.name for d in cur.description]
        rows = cur.fetchall()
    df = pl.DataFrame(rows, schema=cols, orient="row", infer_schema_length=None)
    # NUMERIC z Postgresa przychodzi jako Decimal → Float64 dla wygody
    return df.with_columns([pl.col(c).cast(pl.Float64) for c, t in df.schema.items()
                            if isinstance(t, pl.Decimal)])


def run() -> dict:
    out_dir = REPORTS / "analytics"
    out_dir.mkdir(parents=True, exist_ok=True)
    summary = ["# Wyniki zapytań analitycznych (podgląd)", ""]
    results = {}

    conn = psycopg2.connect(DWH_URL)
    try:
        for sql_file in sorted((SQL_DIR / "analytics").glob("*.sql")):
            df = run_query(conn, sql_file.read_text(encoding="utf-8"))
            df.write_csv(out_dir / f"{sql_file.stem}.csv")
            results[sql_file.stem] = df.height
            log.info("%s: %d wierszy", sql_file.stem, df.height)
            with pl.Config(tbl_formatting="MARKDOWN", tbl_hide_dataframe_shape=True,
                           tbl_hide_column_data_types=True, tbl_cols=-1, tbl_rows=20, tbl_width_chars=1000):
                summary += [f"## {sql_file.stem} ({df.height} wierszy)", "", str(df.head(12)), ""]
    finally:
        conn.close()

    (out_dir / "summary.md").write_text("\n".join(summary), encoding="utf-8")
    return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(run())
