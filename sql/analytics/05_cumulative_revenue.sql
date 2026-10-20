-- =====================================================================
-- 5. Przychód narastający
-- Przychód = cena + fracht (to, co zapłacił klient za pozycje)
-- Funkcje okna: SUM OVER (narastająco od początku i od początku roku - YTD),
-- SUM OVER w partycji kategorii (narastająco per kategoria)
-- =====================================================================
WITH monthly AS (
    SELECT
        date_trunc('month', d.full_date)::date AS month,
        SUM(f.price + f.freight_value)         AS revenue
    FROM fact_order_items f
    JOIN dim_date d ON d.date_key = f.date_key
    WHERE f.order_status NOT IN ('canceled', 'unavailable')
    GROUP BY 1
)
SELECT
    month,
    revenue,
    SUM(revenue) OVER (ORDER BY month ROWS UNBOUNDED PRECEDING)               AS cumulative_revenue,
    SUM(revenue) OVER (PARTITION BY EXTRACT(YEAR FROM month)
                       ORDER BY month ROWS UNBOUNDED PRECEDING)               AS ytd_revenue,
    ROUND(100.0 * SUM(revenue) OVER (ORDER BY month ROWS UNBOUNDED PRECEDING)
          / SUM(revenue) OVER (), 2)                                          AS pct_of_total_to_date
FROM monthly
ORDER BY month;
