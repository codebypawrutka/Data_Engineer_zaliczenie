"""Generator SYNTETYCZNYCH danych w formacie Olist (do testu potoku bez Kaggle).

Tworzy 9 plików CSV z tymi samymi kolumnami co oryginał i celowo wstrzykuje
błędy (ujemne ceny, zły stan, osierocone klucze, duplikaty, złe daty), żeby
było widać działanie testów jakości i kwarantanny.

Użycie (w kontenerze):  python /opt/airflow/tests/make_sample_data.py /opt/airflow/data/raw_sample
UWAGA: do zadania używaj prawdziwych danych z Kaggle w data/raw.
"""
import csv
import random
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path

random.seed(42)
OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "data/raw_sample")
OUT.mkdir(parents=True, exist_ok=True)

STATES = ["SP"] * 8 + ["RJ"] * 3 + ["MG"] * 3 + ["RS", "PR", "SC", "BA", "DF", "GO", "PE", "CE"]
CITIES = {"SP": "sao paulo", "RJ": "rio de janeiro", "MG": "belo horizonte", "RS": "porto alegre",
          "PR": "curitiba", "SC": "florianopolis", "BA": "salvador", "DF": "brasilia",
          "GO": "goiania", "PE": "recife", "CE": "fortaleza"}
CATS = [("cama_mesa_banho", "bed_bath_table"), ("beleza_saude", "health_beauty"),
        ("esporte_lazer", "sports_leisure"), ("informatica_acessorios", "computers_accessories"),
        ("moveis_decoracao", "furniture_decor"), ("utilidades_domesticas", "housewares"),
        ("relogios_presentes", "watches_gifts"), ("telefonia", "telephony"),
        ("automotivo", "auto"), ("brinquedos", "toys")]


def uid():
    return uuid.uuid4().hex


def ts(d):
    return d.strftime("%Y-%m-%d %H:%M:%S") if d else ""


def write(name, header, rows):
    with open(OUT / name, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def zip_for(state):
    return f"{random.randint(1000, 99999):05d}"


# ---------- kategorie (z BOM w nagłówku jak w oryginale) ----------
with open(OUT / "product_category_name_translation.csv", "w", newline="", encoding="utf-8-sig") as f:
    w = csv.writer(f)
    w.writerow(["product_category_name", "product_category_name_english"])
    w.writerows(CATS)

# ---------- sprzedawcy ----------
sellers = []
for _ in range(120):
    st = random.choice(STATES)
    sellers.append([uid(), zip_for(st), CITIES[st], st])
sellers.append([uid(), "123", "xyz", "XX"])          # błąd: zły zip i stan
write("olist_sellers_dataset.csv",
      ["seller_id", "seller_zip_code_prefix", "seller_city", "seller_state"], sellers)
good_sellers = [s[0] for s in sellers[:-1]]
seller_weights = [random.paretovariate(1.2) for _ in good_sellers]

# ---------- produkty ----------
products = []
for _ in range(600):
    cat = random.choice(CATS)[0] if random.random() > 0.02 else ""
    products.append([uid(), cat, random.randint(10, 60), random.randint(50, 2000),
                     random.randint(1, 6), random.randint(100, 20000), random.randint(10, 80),
                     random.randint(2, 60), random.randint(10, 60)])
products[5][5] = -50                                  # błąd: ujemna waga
write("olist_products_dataset.csv",
      ["product_id", "product_category_name", "product_name_lenght", "product_description_lenght",
       "product_photos_qty", "product_weight_g", "product_length_cm", "product_height_cm",
       "product_width_cm"], products)
good_products = [p[0] for i, p in enumerate(products) if i != 5]

# ---------- klienci + zamówienia ----------
customers, orders, items, payments, reviews, geo = [], [], [], [], [], []
people = [(uid(), random.choice(STATES)) for _ in range(3500)]
start = datetime(2016, 10, 1)
for n in range(5000):
    unique_id, st = random.choice(people[:300]) if random.random() < 0.06 else random.choice(people)
    cust_id = uid()
    z = zip_for(st)
    customers.append([cust_id, unique_id, z, CITIES[st].upper() + " ", st.lower()])
    geo.append([z, round(random.uniform(-30, -5), 6), round(random.uniform(-55, -38), 6), CITIES[st], st])
    # trend wzrostowy + pik w listopadzie 2017
    day = int(random.triangular(0, 700, 650))
    purchase = start + timedelta(days=day, seconds=random.randint(0, 86399))
    if random.random() < 0.03:
        purchase = datetime(2017, 11, 24, random.randint(0, 23), random.randint(0, 59))
    status = random.choices(["delivered", "shipped", "canceled", "unavailable", "invoiced"],
                            [92, 3, 2, 1, 2])[0]
    est = purchase + timedelta(days=random.randint(15, 35))
    delivered = purchase + timedelta(days=random.randint(3, 40)) if status == "delivered" else None
    oid = uid()
    orders.append([oid, cust_id, status, ts(purchase), ts(purchase + timedelta(hours=2)),
                   ts(purchase + timedelta(days=2)) if delivered else "", ts(delivered), ts(est)])
    total = 0
    for k in range(1, random.choices([1, 2, 3], [85, 12, 3])[0] + 1):
        price = round(random.lognormvariate(4.3, 0.8), 2)
        freight = round(random.uniform(5, 40), 2)
        total += price + freight
        items.append([oid, k, random.choice(good_products),
                      random.choices(good_sellers, seller_weights)[0],
                      ts(purchase + timedelta(days=5)), price, freight])
    payments.append([oid, 1, random.choice(["credit_card"] * 7 + ["boleto"] * 2 + ["voucher"]),
                     random.randint(1, 10), round(total, 2)])
    reviews.append([uid(), oid, random.choices([1, 2, 3, 4, 5], [10, 3, 8, 19, 60])[0], "", "Muito bom,\nrecomendo",
                    ts(purchase + timedelta(days=10)), ts(purchase + timedelta(days=11))])

# ---------- wstrzyknięte błędy ----------
items.append(items[0])                                            # dokładny duplikat
items.append([orders[1][0], 1, good_products[0], good_sellers[0], ts(start), 10, 5])  # duplikat klucza
items.append([uid(), 1, good_products[0], good_sellers[0], ts(start), 50, 5])        # osierocone zamówienie
items.append([orders[2][0], 9, good_products[0], good_sellers[0], ts(start), -10, 5]) # ujemna cena
items.append([orders[3][0], 8, "nieistniejacy_produkt", good_sellers[0], ts(start), 20, 5])
items.append([orders[4][0], 7, good_products[0], good_sellers[0], ts(start), "abc", 5])  # zły typ
orders[10][6] = ts(datetime(2015, 1, 1))                           # doręczenie przed zakupem
orders[11][2] = "lost"                                             # nieznany status
orders[12][6] = "" ; orders[12][2] = "delivered"                   # delivered bez daty
reviews[0][2] = 7                                                  # ocena spoza 1-5
payments[0][3] = 0                                                 # 0 rat
customers[20][4] = "ZZ"                                            # zły stan
geo.append(["01001", 48.85, 2.35, "paris", "SP"])                  # punkt poza Brazylią
geo += geo[:200]                                                   # duplikaty

write("olist_customers_dataset.csv", ["customer_id", "customer_unique_id", "customer_zip_code_prefix",
      "customer_city", "customer_state"], customers)
write("olist_orders_dataset.csv", ["order_id", "customer_id", "order_status", "order_purchase_timestamp",
      "order_approved_at", "order_delivered_carrier_date", "order_delivered_customer_date",
      "order_estimated_delivery_date"], orders)
write("olist_order_items_dataset.csv", ["order_id", "order_item_id", "product_id", "seller_id",
      "shipping_limit_date", "price", "freight_value"], items)
write("olist_order_payments_dataset.csv", ["order_id", "payment_sequential", "payment_type",
      "payment_installments", "payment_value"], payments)
write("olist_order_reviews_dataset.csv", ["review_id", "order_id", "review_score", "review_comment_title",
      "review_comment_message", "review_creation_date", "review_answer_timestamp"], reviews)
write("olist_geolocation_dataset.csv", ["geolocation_zip_code_prefix", "geolocation_lat", "geolocation_lng",
      "geolocation_city", "geolocation_state"], geo)
print(f"Zapisano 9 plików do {OUT}")
