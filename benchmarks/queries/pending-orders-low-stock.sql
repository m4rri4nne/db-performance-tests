-- Subquery + JOIN: pending orders that contain at least one low-stock item
SELECT DISTINCT o.id     AS order_id,
                o.user_id,
                o.created_at
FROM orders o
WHERE o.status = 'pending'
  AND EXISTS (
      SELECT 1
      FROM order_items oi
      JOIN inventory i ON i.product_id = oi.product_id
      WHERE oi.order_id = o.id
        AND i.stock < :low_stock_threshold
  )
ORDER BY o.created_at;
