# Raport jakości danych (warstwa silver)

Wygenerowano: 2026-10-20T20:32:13  
Próg kwarantanny: 5.0%

## Podsumowanie tabel

| Tabela | Wiersze wej. | Duplikaty usunięte | OK | Kwarantanna | % kwarantanny |
|---|---:|---:|---:|---:|---:|
| category_translation | 71 | 0 | 71 | 0 | 0.0 |
| customers | 99,441 | 0 | 99,441 | 0 | 0.0 |
| sellers | 3,095 | 0 | 3,095 | 0 | 0.0 |
| products | 32,951 | 0 | 32,951 | 0 | 0.0 |
| orders | 99,441 | 0 | 99,433 | 8 | 0.008 |
| order_items | 112,650 | 0 | 112,642 | 8 | 0.007 |
| order_payments | 103,886 | 0 | 103,876 | 10 | 0.01 |
| order_reviews | 99,224 | 0 | 99,216 | 8 | 0.008 |
| geolocation | 1,000,163 | 261,831 | 738,299 | 33 | 0.004 |

## Wyniki testów

| Tabela | Test | Liczba błędów | Status |
|---|---|---:|---|
| category_translation | `category_pk_unique` | 0 | PASS |
| category_translation | `category_english_not_null` | 0 | PASS |
| customers | `customer_pk_unique` | 0 | PASS |
| customers | `customer_unique_id_not_null` | 0 | PASS |
| customers | `customer_state_valid` | 0 | PASS |
| customers | `customer_zip_5_digits` | 0 | PASS |
| sellers | `seller_pk_unique` | 0 | PASS |
| sellers | `seller_state_valid` | 0 | PASS |
| sellers | `seller_zip_5_digits` | 0 | PASS |
| products | `product_pk_unique` | 0 | PASS |
| products | `product_dimensions_non_negative` | 0 | PASS |
| orders | `order_pk_unique` | 0 | PASS |
| orders | `order_status_valid` | 0 | PASS |
| orders | `order_purchase_ts_not_null` | 0 | PASS |
| orders | `order_fk_customer` | 0 | PASS |
| orders | `order_delivered_after_purchase` | 0 | PASS |
| orders | `order_delivered_has_date` | 8 | FAIL → kwarantanna |
| order_items | `item_pk_unique` | 0 | PASS |
| order_items | `item_price_positive` | 0 | PASS |
| order_items | `item_fk_order` | 8 | FAIL → kwarantanna |
| order_items | `item_fk_product` | 0 | PASS |
| order_items | `item_fk_seller` | 0 | PASS |
| order_payments | `payment_pk_unique` | 0 | PASS |
| order_payments | `payment_type_valid` | 0 | PASS |
| order_payments | `payment_value_non_negative` | 0 | PASS |
| order_payments | `payment_installments_positive` | 2 | FAIL → kwarantanna |
| order_payments | `payment_fk_order` | 8 | FAIL → kwarantanna |
| order_reviews | `review_pk_unique` | 0 | PASS |
| order_reviews | `review_score_1_5` | 0 | PASS |
| order_reviews | `review_fk_order` | 8 | FAIL → kwarantanna |
| geolocation | `geo_zip_5_digits` | 0 | PASS |
| geolocation | `geo_lat_in_brazil` | 27 | FAIL → kwarantanna |
| geolocation | `geo_lng_in_brazil` | 29 | FAIL → kwarantanna |
| geolocation | `geo_state_valid` | 0 | PASS |

Łącznie testów: **34**. Błędne wiersze: `data/lake/quarantine/<tabela>/` (kolumna `_failed_rules` mówi, które reguły nie przeszły).
