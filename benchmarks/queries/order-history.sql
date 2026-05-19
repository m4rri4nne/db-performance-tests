SELECT o.id, o.status, o.total, o.created_at
FROM orders o
WHERE o.user_id = :user_id
ORDER BY o.created_at DESC
LIMIT 20;
