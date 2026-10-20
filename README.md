# Olist: lokalny potok danych e-commerce

Lokalny potok danych na zbiorze [Brazilian E-Commerce Public Dataset (Olist)](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce). Działa w całości na jednym komputerze, bez AWS i Databricks:

- **jezioro danych:** katalog `data/lake` z warstwami bronze, silver i gold w formacie Parquet;
- **hurtownia:** PostgreSQL 16 w Dockerze z modelem gwiazdy;
- **przetwarzanie:** Polars (bronze/silver) i PySpark w trybie `local[*]` (gold);
- **orkiestracja:** Apache Airflow 3 (DAG `olist_pipeline`).

```
data/raw/*.csv ──► bronze (Polars, jawne typy) ──► silver (czyszczenie + 34 testy DQ)
                                                     │        ├──► quarantine/ (błędne wiersze)
                                                     │        └──► reports/dq_report.md
                                     ┌───────────────┴───────────────┐
                                     ▼                               ▼
                    PostgreSQL: model gwiazdy                gold (PySpark, partycje)
                                     ▼
                    5 zapytań analitycznych → reports/analytics/*.csv
```

---

## 1. Instalacja na Windows 

### 1.1 Wymagania

WSL2 i Docker Desktop są już zainstalowane.

```powershell
wsl --status
docker version
docker compose version     # wymagane v2.24 lub nowsze
```

### 1.2 Przeniesienie danych Dockera na dysk J: (jednorazowo)

### 1.3 Projekt

Struktura katalogów:

```
J:\olist-pipeline
├── docker-compose.yml        # Postgres + Airflow
├── Dockerfile                # obraz Airflow + Java + Polars + PySpark
├── requirements.txt
├── .env.example              # (opcjonalnie) dane do Kaggle API
├── docker\init.sql           # tworzy bazę metadanych Airflow
├── dags\olist_pipeline.py    # DAG
├── src\olist\                # kod kroków potoku
│   ├── config.py             # ścieżki, połączenie, próg kwarantanny
│   ├── download.py           # krok 0: pobranie z Kaggle (lub pominięcie)
│   ├── bronze.py             # krok 1: CSV → Parquet z jawnymi typami
│   ├── silver.py             # krok 2: czyszczenie, testy DQ, kwarantanna, raport
│   ├── load_dwh.py           # krok 3: model gwiazdy → Postgres
│   ├── analytics.py          # krok 4: 5 zapytań → CSV
│   └── gold_spark.py         # krok 5: 2 tabele gold (PySpark, partycje)
├── sql\
│   ├── ddl_star_schema.sql   # definicja modelu gwiazdy
│   └── analytics\01..05_*.sql
├── tests\make_sample_data.py # generator danych syntetycznych (test bez Kaggle)
├── docs\analysis.md          # TU piszesz analizę wyników
├── data\                     # jezioro danych (tworzone przez potok)
│   ├── raw\                  # ← tu wrzucasz CSV z Kaggle
│   ├── lake\bronze|silver|gold|quarantine\
│   └── reports\
└── logs\                     # logi Airflow
```

### 1.4 Dane z Kaggle 

Pliki w `data\raw`:
```
olist_customers_dataset.csv        olist_orders_dataset.csv
olist_geolocation_dataset.csv      olist_products_dataset.csv
olist_order_items_dataset.csv      olist_sellers_dataset.csv
olist_order_payments_dataset.csv   product_category_name_translation.csv
olist_order_reviews_dataset.csv
```

### 1.5 Uruchomienie kontenerów

W PowerShellu:

```powershell
cd J:\olist-pipeline
docker compose up -d --build      # pierwsze budowanie obrazu
docker compose ps                 # oba kontenery: running, warehouse: healthy
docker compose logs -f airflow    
```

Otwieramy **http://localhost:8080**. Lokalnie UI działa bez logowania.

---

## 2. Uruchomienie potoku

1. W UI Airflow znajdujemy DAG **`olist_pipeline`**.
2. Klikamy na uruchom co później potwierdzamy.
3. W widoku **Graph** kolejne taski zmieniają kolor na zielony. 

Kroki można też uruchamiać pojedynczo z PowerShella

```powershell
docker compose exec airflow python -m olist.bronze
docker compose exec airflow python -m olist.silver
docker compose exec airflow python -m olist.load_dwh
docker compose exec airflow python -m olist.analytics
docker compose exec airflow python -m olist.gold_spark
```

**Test bez Kaggle (dane syntetyczne z wstrzykniętymi błędami):**

```powershell
docker compose exec airflow python /opt/airflow/tests/make_sample_data.py /opt/airflow/data/raw
```

Następnie uruchom DAG. 

### Gdzie są wyniki

| Co | Gdzie (Windows) |
|---|---|
| Bronze | `J:\olist-pipeline\data\lake\bronze\<tabela>\data.parquet` |
| Silver | `J:\olist-pipeline\data\lake\silver\<tabela>\data.parquet` |
| Kwarantanna | `J:\olist-pipeline\data\lake\quarantine\<tabela>\data.parquet` (kolumna `_failed_rules`) |
| Raport DQ | `J:\olist-pipeline\data\reports\dq_report.md` i `.json` |
| Gold | `J:\olist-pipeline\data\lake\gold\sales_daily_by_category\year=…\month=…\` oraz `...\seller_monthly_kpi\seller_state=…\` |
| Wyniki zapytań | `J:\olist-pipeline\data\reports\analytics\*.csv` i `summary.md` |
| Hurtownia | Postgres `localhost:5432`, baza `olist_dwh`, użytkownik/hasło `dwh` / `dwh` |
| Logi Airflow | `J:\olist-pipeline\logs\` lub w UI (kliknij task → Logs) |

**DBeaver:** New Connection → PostgreSQL → Host `localhost`, Port `5432`, Database `olist_dwh`, User `dwh`, Password `dwh`.

---

## 3. Co dzieje się w każdym kroku

# Krok 1: `ingest_bronze` (Polars)
- Każdy CSV jest czytany jako tekst (`infer_schema=False`), więc bez zgadywania typów.
- Każda kolumna jest rzutowana na **jawnie zapisany typ** (`SCHEMAS` w `bronze.py`). Przykład: kody pocztowe zostają tekstem, żeby nie zgubić zer wiodących, a daty są parsowane według formatu `%Y-%m-%d %H:%M:%S`.
- Wartość, której nie da się zrzutować, staje się `NULL`. Liczba takich przypadków trafia do `reports/bronze_ingest.json` (`cast_failures`), a złe wiersze wyłapie silver.
- Do danych dochodzą kolumny techniczne `_ingested_at` i `_source_file` (lineage). Usuwany jest też BOM z nagłówków.

# Krok 2: `build_silver_with_dq`
1. **Czyszczenie:** trim, miasta małymi literami, stany wielkimi, usunięcie identycznych duplikatów, poprawka literówek w nazwach kolumn (`lenght` → `length`), dołączenie angielskich nazw kategorii, agregacja geolokalizacji do jednego punktu na prefiks kodu.
2. **34 testy jakości** w 9 tabelach. Główne z nich:

   | Test | Tabela | Reguła |
   |---|---|---|
   | `*_pk_unique` | wszystkie | klucz główny niepusty i unikalny |
   | `order_status_valid` | orders | status z dozwolonej listy |
   | `order_delivered_after_purchase` | orders | doręczenie ≥ zakup |
   | `order_delivered_has_date` | orders | status `delivered` musi mieć datę doręczenia |
   | `item_price_positive` | order_items | cena > 0, fracht ≥ 0 |
   | `item_fk_order/product/seller` | order_items | integralność referencyjna |
   | `*_state_valid` | customers, sellers, geolocation | jeden z 27 stanów Brazylii |
   | `*_zip_5_digits` | customers, sellers, geolocation | kod = 5 cyfr |
   | `review_score_1_5` | order_reviews | ocena 1–5 |
   | `payment_installments_positive` | order_payments | liczba rat ≥ 1 |
   | `geo_lat/lng_in_brazil` | geolocation | współrzędne w granicach Brazylii |

3. **Kwarantanna:** wiersz z co najmniej jednym błędem trafia do `quarantine/<tabela>` z listą nieudanych reguł, a nie do silver. Testy integralności sprawdzają klucze względem już oczyszczonych tabel. Dzięki temu pozycje zamówienia, które zostało odrzucone, też lądują w kwarantannie, a model pozostaje spójny.
4. **Raport:** `dq_report.md` i `dq_report.json` (oraz kopia z datą i godziną).
5. **Bezpiecznik:** jeśli odsetek kwarantanny w którejś tabeli przekroczy `MAX_QUARANTINE_PCT` (domyślnie 5%), task kończy się błędem i dalsze kroki się nie wykonują. W hurtowni zostają wtedy poprzednie, dobre dane.

### Krok 3: `load_star_schema`
- **Model gwiazdy** (`sql/ddl_star_schema.sql`):
  - `fact_order_items`: ziarno to jedna pozycja zamówienia. Zawiera cenę, fracht, dni dostawy i flagę spóźnienia.
  - `dim_customer`: zawiera `customer_unique_id`, czyli prawdziwego klienta, plus współrzędne.
  - `dim_seller`, `dim_product` (kategoria PT/EN, `unknown` przy braku), `dim_date` (kalendarz).
- Klucze surogatowe są nadawane w Pythonie, deterministycznie.
- Ładowanie odbywa się w **jednej transakcji**: `TRUNCATE` + `COPY` (szybkie ładowanie hurtowe). Każde uruchomienie daje ten sam wynik (idempotencja), a przy błędzie następuje rollback.
- Płatności celowo nie trafiają do faktu. Są per zamówienie, nie per pozycję, więc ich doklejenie zdublowałoby kwoty.

### Krok 4: `run_analytics`
Wykonuje `sql/analytics/*.sql` (CTE + funkcje okna) i zapisuje wyniki do CSV:

| Plik | Pytanie biznesowe | Funkcje okna |
|---|---|---|
| `01_gmv_mom.sql` | GMV miesiąc do miesiąca | `LAG`, `AVG OVER` (średnia krocząca 3M) |
| `02_top3_categories_by_state.sql` | top 3 kategorie w każdym stanie | `DENSE_RANK`, `SUM OVER (PARTITION BY)` |
| `03_seller_ranking.sql` | ranking sprzedawców, Pareto | `RANK`, `NTILE`, `ROW_NUMBER`, suma narastająca |
| `04_customer_retention.sql` | retencja w kohortach miesięcznych | `MIN OVER`, `FIRST_VALUE`, `WINDOW` |
| `05_cumulative_revenue.sql` | przychód narastający i YTD | `SUM OVER (ROWS UNBOUNDED PRECEDING)` |

Przyjęte definicje: **GMV** to suma `price`, **przychód** to `price + freight_value`. Zamówienia `canceled` i `unavailable` są wykluczone.

### Krok 5: `build_gold_spark` (PySpark local)
Spark działa w osobnym procesie (`python -m olist.gold_spark`), czyta silver i zapisuje dwie tabele:

- `gold/sales_daily_by_category`: dzienna sprzedaż per kategoria, **partycje `year/month`** (typowe zapytania są „za okres”).
- `gold/seller_monthly_kpi`: miesięczne KPI sprzedawców (GMV, zamówienia, dni dostawy, % spóźnień), **partycja `seller_state`** (dashboardy regionalne).

Na końcu krok sam sprawdza, że odczyt z filtrem po partycji korzysta z partition pruning (`partition_pruning_used: True` w logu).

---


## 6. Przeniesienie do chmury (szkic)

Gdybym miał przenieść ten potok do chmury, wybrałbym AWS, bo o nim najwięcej do tej pory czytałem. Zamiast katalogu data/lake na dysku użyłbym S3. Zostawiłbym ten sam podział na foldery bronze, silver i gold, więc sama idea warstw by się nie zmieniła. Zamiast zwykłych plików Parquet spróbowałbym użyć Delta Lake. Z tego, co rozumiem, pozwala on aktualizować dane zamiast za każdym razem nadpisywać wszystko od nowa, a do tego można wrócić do wcześniejszej wersji tabeli, jeśli coś pójdzie nie tak. Skrypty w Polars i PySparku uruchamiałbym w AWS Glue albo w Databricks, bo tam Spark działa na wielu maszynach naraz, a nie tylko na moim komputerze. Postgresa w Dockerze zamieniłbym na hurtownię w chmurze, np. Redshift albo Snowflake, które są przygotowane do analizy dużych ilości danych. Airflow nie musiałbym wtedy instalować sam, bo AWS ma gotową usługę MWAA. Hasła, które teraz są wpisane w docker-compose.yml, trzymałbym w AWS Secrets Manager, bo w prawdziwym projekcie nie powinny leżeć w kodzie. Na razie każde uruchomienie potoku ładuje wszystkie dane od początku. Przy małym zbiorze to wystarcza, ale przy dużych danych trwałoby za długo, więc docelowo chciałbym ładować tylko nowe zamówienia, np. z ostatniego dnia. Tego jeszcze nie umiem dobrze zrobić i to jest jedna z rzeczy, których chcę się nauczyć w następnej kolejności.
