-- Aggregation: order counts per status, scoped to a date range
SELECT status,
       COUNT(*)        AS order_count,
       SUM(total)      AS total_value,
       MIN(created_at) AS first_order,
       MAX(created_at) AS last_order
FROM orders
WHERE created_at >= :start_date
  AND created_at <  :end_date
GROUP BY status
ORDER BY order_count DESC;
