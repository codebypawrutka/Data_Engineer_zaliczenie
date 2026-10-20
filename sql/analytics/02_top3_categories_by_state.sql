-- =====================================================================
-- 2. Top 3 kategorie produktów w każdym stanie (stan KLIENTA)
-- Funkcje okna: DENSE_RANK w partycji stanu, udział kategorii w GMV stanu
-- =====================================================================
WITH category_state AS (
    SELECT
        c.state,
        p.category_name_en           AS category,
        SUM(f.price)                 AS gmv,
        COUNT(DISTINCT f.order_id)   AS orders
    FROM fact_order_items f
    JOIN dim_customer c ON c.customer_key = f.customer_key
    JOIN dim_product  p ON p.product_key  = f.product_key
    WHERE f.order_status NOT IN ('canceled', 'unavailable')
    GROUP BY c.state, p.category_name_en
),
ranked AS (
    SELECT
        state,
        category,
        gmv,
        orders,
        DENSE_RANK() OVER (PARTITION BY state ORDER BY gmv DESC)         AS rank_in_state,
        ROUND(100.0 * gmv / SUM(gmv) OVER (PARTITION BY state), 2)        AS share_of_state_pct,
        SUM(gmv) OVER (PARTITION BY state)                                AS state_total_gmv
    FROM category_state
)
SELECT state, rank_in_state, category, gmv, orders, share_of_state_pct, state_total_gmv
FROM ranked
WHERE rank_in_state <= 3
ORDER BY state_total_gmv DESC, state, rank_in_state;
