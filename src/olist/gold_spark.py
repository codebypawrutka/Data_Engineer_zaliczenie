"""Krok 5: GOLD — dwie partycjonowane tabele w PySparku (tryb local).

Co się dzieje:
1. Spark startuje lokalnie (master local[*] = jeden proces JVM, wszystkie rdzenie CPU).
2. Czyta parquety z warstwy silver, łączy pozycje zamówień z zamówieniami,
   produktami i sprzedawcami.
3. Zapisuje dwie tabele z partycjonowaniem katalogowym (Hive-style):
   - gold/sales_daily_by_category/year=2017/month=11/part-*.parquet
     dzienna sprzedaż per kategoria — zapytania "za okres" czytają tylko
     potrzebne katalogi (partition pruning)
   - gold/seller_monthly_kpi/seller_state=SP/part-*.parquet
     miesięczne KPI sprzedawców — dashboard regionalny czyta jeden stan
4. Tryb overwrite = pełne przeliczenie przy każdym uruchomieniu (idempotencja).
5. Na koniec weryfikacja: odczyt z filtrem po partycji + plan zapytania.
"""
import logging

from pyspark.sql import SparkSession
from pyspark.sql import functions as F

from olist.config import GOLD, SILVER

log = logging.getLogger(__name__)

EXCLUDED_STATUSES = ["canceled", "unavailable"]


def get_spark() -> SparkSession:
    return (
        SparkSession.builder.master("local[*]")
        .appName("olist_gold")
        .config("spark.driver.memory", "2g")
        .config("spark.sql.shuffle.partitions", "8")   # małe dane → mało partycji shuffle
        .config("spark.sql.session.timeZone", "UTC")
        .config("spark.ui.enabled", "false")
        .getOrCreate()
    )


def run() -> dict:
    spark = get_spark()
    spark.sparkContext.setLogLevel("WARN")
    try:
        items = spark.read.parquet(str(SILVER / "order_items"))
        orders = spark.read.parquet(str(SILVER / "orders"))
        products = spark.read.parquet(str(SILVER / "products"))
        sellers = spark.read.parquet(str(SILVER / "sellers"))

        base = (
            items.join(orders, "order_id")
            .join(products.select("product_id", "product_category_name",
                                  "product_category_name_english"), "product_id", "left")
            .filter(~F.col("order_status").isin(EXCLUDED_STATUSES))
            .withColumn("category", F.coalesce("product_category_name_english",
                                               "product_category_name", F.lit("unknown")))
            .withColumn("order_date", F.to_date("order_purchase_timestamp"))
            .withColumn("year", F.year("order_date"))
            .withColumn("month", F.month("order_date"))
            .withColumn("delivery_days", F.datediff(F.to_date("order_delivered_customer_date"),
                                                    F.col("order_date")))
        ).cache()

        # ---------- GOLD 1: dzienna sprzedaż per kategoria, partycje year/month ----------
        sales_daily = (
            base.groupBy("year", "month", "order_date", "category")
            .agg(
                F.round(F.sum("price"), 2).alias("gmv"),
                F.round(F.sum("freight_value"), 2).alias("freight"),
                F.round(F.sum(F.col("price") + F.col("freight_value")), 2).alias("revenue"),
                F.countDistinct("order_id").alias("orders"),
                F.count("*").alias("items"),
                F.round(F.avg("price"), 2).alias("avg_item_price"),
            )
        )
        path1 = str(GOLD / "sales_daily_by_category")
        (sales_daily.repartition("year", "month")       # 1 plik na partycję zamiast wielu małych
         .write.mode("overwrite").partitionBy("year", "month").parquet(path1))

        # ---------- GOLD 2: miesięczne KPI sprzedawców, partycja seller_state ----------
        seller_kpi = (
            base.join(sellers.select("seller_id", "seller_state", "seller_city"), "seller_id")
            .withColumn("order_month", F.date_format("order_date", "yyyy-MM"))
            .groupBy("seller_state", "seller_id", "seller_city", "order_month")
            .agg(
                F.round(F.sum("price"), 2).alias("gmv"),
                F.countDistinct("order_id").alias("orders"),
                F.count("*").alias("items"),
                F.countDistinct("category").alias("distinct_categories"),
                F.round(F.avg("delivery_days"), 1).alias("avg_delivery_days"),
                F.round(100 * F.avg(F.when(
                    F.col("order_delivered_customer_date") > F.col("order_estimated_delivery_date"), 1
                ).when(F.col("order_delivered_customer_date").isNotNull(), 0)), 1).alias("late_pct"),
            )
        )
        path2 = str(GOLD / "seller_monthly_kpi")
        (seller_kpi.repartition("seller_state")
         .write.mode("overwrite").partitionBy("seller_state").parquet(path2))

        base.unpersist()

        # ---------- Weryfikacja: odczyt z filtrem po partycji ----------
        check = spark.read.parquet(path1).filter((F.col("year") == 2017) & (F.col("month") == 11))
        plan = check._jdf.queryExecution().executedPlan().toString()
        pruned = "PartitionFilters" in plan and "year" in plan
        result = {
            "sales_daily_by_category_rows": spark.read.parquet(path1).count(),
            "seller_monthly_kpi_rows": spark.read.parquet(path2).count(),
            "nov_2017_rows_via_partition_filter": check.count(),
            "partition_pruning_used": pruned,
        }
        log.info("gold: %s", result)
        print(result)
        return result
    finally:
        spark.stop()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run()
