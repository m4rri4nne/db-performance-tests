-- Subquery: retrieve each user's first order (useful for cohort analysis)
SELECT u.id, u.email, u.country, first_order.id AS order_id, first_order.total, first_order.created_at
FROM users u
JOIN orders first_order ON first_order.id = (
    SELECT id
    FROM orders
    WHERE user_id = u.id
    ORDER BY created_at ASC
    LIMIT 1
)
WHERE u.country = :country;
