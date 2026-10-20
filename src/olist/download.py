"""Krok 0: pobranie CSV z Kaggle do data/raw.

Jeśli wszystkie pliki już są w data/raw (np. pobrane ręcznie przez przeglądarkę),
krok nic nie robi. W przeciwnym razie używa Kaggle API — wymaga zmiennych
KAGGLE_USERNAME i KAGGLE_KEY (ustawiane w pliku .env).
"""
import logging
import os

from olist.config import KAGGLE_DATASET, RAW

log = logging.getLogger(__name__)

EXPECTED_FILES = [
    "olist_customers_dataset.csv",
    "olist_geolocation_dataset.csv",
    "olist_order_items_dataset.csv",
    "olist_order_payments_dataset.csv",
    "olist_order_reviews_dataset.csv",
    "olist_orders_dataset.csv",
    "olist_products_dataset.csv",
    "olist_sellers_dataset.csv",
    "product_category_name_translation.csv",
]


def missing_files() -> list[str]:
    return [f for f in EXPECTED_FILES if not (RAW / f).exists()]


def run() -> dict:
    RAW.mkdir(parents=True, exist_ok=True)
    missing = missing_files()
    if not missing:
        log.info("Wszystkie %d pliki CSV są już w %s — pomijam pobieranie.", len(EXPECTED_FILES), RAW)
        return {"downloaded": False, "files": len(EXPECTED_FILES)}

    if not (os.environ.get("KAGGLE_USERNAME") and os.environ.get("KAGGLE_KEY")):
        raise RuntimeError(
            f"Brakuje plików w {RAW}: {missing}. Pobierz ZIP ręcznie z Kaggle i rozpakuj "
            "do J:\\olist-pipeline\\data\\raw albo ustaw KAGGLE_USERNAME i KAGGLE_KEY w pliku .env."
        )

    from kaggle.api.kaggle_api_extended import KaggleApi  # import tutaj: autoryzacja przy imporcie

    api = KaggleApi()
    api.authenticate()
    log.info("Pobieram %s do %s ...", KAGGLE_DATASET, RAW)
    api.dataset_download_files(KAGGLE_DATASET, path=str(RAW), unzip=True)

    still_missing = missing_files()
    if still_missing:
        raise RuntimeError(f"Po pobraniu nadal brakuje: {still_missing}")
    return {"downloaded": True, "files": len(EXPECTED_FILES)}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(run())
