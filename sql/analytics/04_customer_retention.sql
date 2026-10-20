-- =====================================================================
-- 4. Retencja klientów — kohorty miesięczne
-- Klient = customer_unique_id (customer_id w Olist jest per zamówienie!)
-- Kohorta = miesiąc pierwszego zakupu; month_number = ile miesięcy później
-- Funkcje okna: MIN OVER (kohorta klienta), FIRST_VALUE (wielkość kohorty)
-- =====================================================================
WITH customer_months AS (
    SELECT DISTINCT
        c.customer_unique_id,
        date_trunc('month', d.full_date)::date AS order_month
    FROM fact_order_items f
    JOIN dim_customer c ON c.customer_key = f.customer_key
    JOIN dim_date     d ON d.date_key     = f.date_key
    WHERE f.order_status NOT IN ('canceled', 'unavailable')
),
with_cohort AS (
    SELECT
        customer_unique_id,
        order_month,
        MIN(order_month) OVER (PARTITION BY customer_unique_id) AS cohort_month
    FROM customer_months
),
cohort_activity AS (
    SELECT
        cohort_month,
        ((EXTRACT(YEAR  FROM order_month) - EXTRACT(YEAR  FROM cohort_month)) * 12
        + (EXTRACT(MONTH FROM order_month) - EXTRACT(MONTH FROM cohort_month)))::int AS month_number,
        COUNT(DISTINCT customer_unique_id) AS active_customers
    FROM with_cohort
    GROUP BY 1, 2
)
SELECT
    cohort_month,
    month_number,
    active_customers,
    FIRST_VALUE(active_customers) OVER w                               AS cohort_size,
    ROUND(100.0 * active_customers / FIRST_VALUE(active_customers) OVER w, 2) AS retention_pct
FROM cohort_activity
WINDOW w AS (PARTITION BY cohort_month ORDER BY month_number)
ORDER BY cohort_month, month_number;
