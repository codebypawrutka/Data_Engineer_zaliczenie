-- =====================================================================
-- 3. Ranking sprzedawców + analiza Pareto
-- Funkcje okna: RANK globalny i w stanie, NTILE (decyle),
-- udział narastający (ile sprzedawców robi 80% GMV)
-- =====================================================================
WITH seller_stats AS (
    SELECT
        f.seller_key,
        SUM(f.price)                                  AS gmv,
        COUNT(DISTINCT f.order_id)                    AS orders,
        ROUND(AVG(f.delivery_days), 1)                AS avg_delivery_days,
        ROUND(100.0 * AVG(f.is_late::int), 1)         AS late_pct
    FROM fact_order_items f
    WHERE f.order_status NOT IN ('canceled', 'unavailable')
    GROUP BY f.seller_key
),
ranked AS (
    SELECT
        s.seller_id,
        s.state                                                   AS seller_state,
        st.gmv,
        st.orders,
        st.avg_delivery_days,
        st.late_pct,
        RANK()  OVER (ORDER BY st.gmv DESC)                       AS rank_global,
        RANK()  OVER (PARTITION BY s.state ORDER BY st.gmv DESC)  AS rank_in_state,
        NTILE(10) OVER (ORDER BY st.gmv DESC)                     AS gmv_decile,
        ROUND(100.0 * SUM(st.gmv) OVER (ORDER BY st.gmv DESC, s.seller_id
                                        ROWS UNBOUNDED PRECEDING)
              / SUM(st.gmv) OVER (), 2)                           AS cumulative_gmv_share_pct,
        ROUND(100.0 * ROW_NUMBER() OVER (ORDER BY st.gmv DESC, s.seller_id)
              / COUNT(*) OVER (), 2)                              AS cumulative_seller_share_pct
    FROM seller_stats st
    JOIN dim_seller s ON s.seller_key = st.seller_key
)
SELECT *
FROM ranked
ORDER BY rank_global;
