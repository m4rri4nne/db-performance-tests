-- JOIN: inventory details enriched with recent sales volume
SELECT i.product_id,
       i.name,
       i.category,
       i.stock,
       SUM(oi.quantity) AS units_sold
FROM inventory i
LEFT JOIN order_items oi ON oi.product_id = i.product_id
WHERE i.category = :category
GROUP BY i.product_id, i.name, i.category, i.stock
ORDER BY units_sold DESC NULLS LAST
LIMIT 50;
