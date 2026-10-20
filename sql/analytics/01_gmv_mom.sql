-- =====================================================================
-- 1. GMV miesiąc do miesiąca (MoM)
-- GMV = suma cen towarów (bez frachtu), bez zamówień anulowanych/niedostępnych.
-- Okres 2017-01 .. 2018-08: miesiące brzegowe (2016 i 09-10.2018) są
-- niekompletne w zbiorze i dawałyby fałszywe skoki MoM.
-- Funkcje okna: LAG (poprzedni miesiąc), AVG OVER (średnia krocząca 3M)
-- =====================================================================
WITH params AS (
    SELECT DATE '2017-01-01' AS date_from, DATE '2018-09-01' AS date_to
),
monthly AS (
    SELECT
        date_trunc('month', d.full_date)::date AS month,
        SUM(f.price)                           AS gmv,
        COUNT(DISTINCT f.order_id)             AS orders,
        COUNT(*)                               AS items
    FROM fact_order_items f
    JOIN dim_date d ON d.date_key = f.date_key
    CROSS JOIN params p
    WHERE f.order_status NOT IN ('canceled', 'unavailable')
      AND d.full_date >= p.date_from AND d.full_date < p.date_to
    GROUP BY 1
)
SELECT
    month,
    gmv,
    orders,
    ROUND(gmv / orders, 2)                                         AS avg_order_value,
    LAG(gmv) OVER (ORDER BY month)                                 AS prev_month_gmv,
    gmv - LAG(gmv) OVER (ORDER BY month)                           AS gmv_change,
    ROUND(100.0 * (gmv - LAG(gmv) OVER (ORDER BY month))
          / NULLIF(LAG(gmv) OVER (ORDER BY month), 0), 2)          AS mom_pct,
    ROUND(AVG(gmv) OVER (ORDER BY month
          ROWS BETWEEN 2 PRECEDING AND CURRENT ROW), 2)            AS gmv_ma_3m
FROM monthly
ORDER BY month;
