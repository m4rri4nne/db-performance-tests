-- Aggregation: top-selling products by revenue within a date range
SELECT oi.product_id,
       i.name,
       SUM(oi.quantity)          AS units_sold,
       SUM(oi.quantity * oi.price) AS revenue
FROM order_items oi
JOIN inventory i  ON i.product_id = oi.product_id
JOIN orders    o  ON o.id = oi.order_id
WHERE o.status IN ('paid', 'shipped')
  AND o.created_at >= :start_date
  AND o.created_at <  :end_date
GROUP BY oi.product_id, i.name
ORDER BY revenue DESC
LIMIT 20;
