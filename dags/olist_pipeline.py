"""DAG Airflow spinający cały potok Olist.

Kolejność:
    download_raw → ingest_bronze → build_silver_with_dq ─┬→ load_star_schema → run_analytics
                                                         └→ build_gold_spark

- load_star_schema i build_gold_spark działają RÓWNOLEGLE (oba zależą tylko od silver).
- build_silver_with_dq kończy się błędem, gdy kwarantanna przekroczy próg — wtedy
  nic dalej się nie wykona, a w hurtowni zostają poprzednie (dobre) dane.
- build_gold_spark uruchamiany jest jako osobny proces (python -m), żeby JVM Sparka
  nie żyła w procesie workera Airflow.
"""
from datetime import datetime, timedelta

from airflow.sdk import dag, task

DEFAULT_ARGS = {
    "owner": "pawel",
    "retries": 1,
    "retry_delay": timedelta(minutes=1),
}


@dag(
    dag_id="olist_pipeline",
    description="Olist: CSV → bronze → silver (DQ) → hurtownia (gwiazda) + gold (PySpark)",
    schedule=None,                 # uruchamiasz ręcznie przyciskiem Trigger; można dać "@daily"
    start_date=datetime(2026, 1, 1),
    catchup=False,
    max_active_runs=1,
    default_args=DEFAULT_ARGS,
    tags=["olist", "portfolio"],
    doc_md=__doc__,
)
def olist_pipeline():

    @task
    def download_raw() -> dict:
        from olist.download import run
        return run()

    @task
    def ingest_bronze() -> list:
        from olist.bronze import run
        return run()

    @task
    def build_silver_with_dq() -> dict:
        from olist.silver import run
        return run()

    @task
    def load_star_schema() -> dict:
        from olist.load_dwh import run
        return run()

    @task
    def run_analytics() -> dict:
        from olist.analytics import run
        return run()

    @task.bash
    def build_gold_spark() -> str:
        return "python -m olist.gold_spark"

    raw = download_raw()
    bronze = ingest_bronze()
    silver = build_silver_with_dq()

    raw >> bronze >> silver
    silver >> load_star_schema() >> run_analytics()
    silver >> build_gold_spark()


olist_pipeline()
