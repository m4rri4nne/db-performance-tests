-- Aggregation: total revenue grouped by user country
SELECT u.country,
       COUNT(DISTINCT o.id)   AS order_count,
       SUM(o.total)           AS total_revenue,
       AVG(o.total)           AS avg_order_value
FROM users u
JOIN orders o ON o.user_id = u.id
WHERE o.status = 'paid'
GROUP BY u.country
ORDER BY total_revenue DESC;
