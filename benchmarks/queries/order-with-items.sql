-- JOIN: full order detail with line items
SELECT o.id, o.status, o.total, o.created_at,
       oi.product_id, oi.quantity, oi.price
FROM orders o
JOIN order_items oi ON oi.order_id = o.id
WHERE o.id = :order_id;
