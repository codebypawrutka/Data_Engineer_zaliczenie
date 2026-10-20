"""Wspólna konfiguracja potoku: ścieżki do jeziora danych i parametry jakości."""
import os
from pathlib import Path

# W kontenerze DATA_DIR=/opt/airflow/data (podmontowane z J:\olist-pipeline\data)
DATA_DIR = Path(os.environ.get("DATA_DIR", Path(__file__).resolve().parents[2] / "data"))
SQL_DIR = Path(os.environ.get("SQL_DIR", Path(__file__).resolve().parents[2] / "sql"))

RAW = DATA_DIR / "raw"
LAKE = DATA_DIR / "lake"
BRONZE = LAKE / "bronze"
SILVER = LAKE / "silver"
GOLD = LAKE / "gold"
QUARANTINE = LAKE / "quarantine"
REPORTS = DATA_DIR / "reports"

# Połączenie z hurtownią (Postgres w Dockerze). Z Windowsa: localhost:5432
DWH_URL = os.environ.get("DWH_URL", "postgresql://dwh:dwh@localhost:5432/olist_dwh")

# Jeśli w kwarantannie wyląduje więcej niż X% wierszy którejkolwiek tabeli,
# krok silver kończy się błędem i zatrzymuje cały DAG ("bezpiecznik").
MAX_QUARANTINE_PCT = float(os.environ.get("MAX_QUARANTINE_PCT", "5"))

KAGGLE_DATASET = "olistbr/brazilian-ecommerce"


def table_dir(layer: Path, table: str) -> Path:
    path = layer / table
    path.mkdir(parents=True, exist_ok=True)
    return path
