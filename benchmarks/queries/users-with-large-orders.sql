-- Subquery: users whose lifetime spend exceeds a threshold
SELECT u.id, u.email, u.country, lifetime.total_spent
FROM users u
JOIN (
    SELECT user_id, SUM(total) AS total_spent
    FROM orders
    WHERE status IN ('paid', 'shipped')
    GROUP BY user_id
    HAVING SUM(total) > :min_spend
) lifetime ON lifetime.user_id = u.id
ORDER BY lifetime.total_spent DESC;
