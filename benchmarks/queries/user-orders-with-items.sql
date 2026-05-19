-- JOIN: all orders and items for a user, newest first
SELECT o.id        AS order_id,
       o.status,
       o.created_at,
       oi.product_id,
       oi.quantity,
       oi.price
FROM orders o
JOIN order_items oi ON oi.order_id = o.id
WHERE o.user_id = :user_id
ORDER BY o.created_at DESC, oi.product_id;
