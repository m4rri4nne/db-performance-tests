SELECT product_id, name, stock
FROM inventory
WHERE category = :category AND stock > 0
ORDER BY stock DESC
LIMIT 50;
