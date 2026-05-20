-- Migration v2: add performance indexes
--
-- Run the regression report BEFORE applying this migration to capture the
-- baseline, then run it AGAIN after to measure the improvement.
--
--   python reports/query_regression_report.py low
--   python scripts/setup_schema.py --schema v2_add_indexes/002_add_indexes
--   python reports/query_regression_report.py low

-- Speeds up order_history queries (user_id filter + created_at sort)
CREATE INDEX IF NOT EXISTS idx_orders_user_created
    ON orders(user_id, created_at DESC);

-- Speeds up JOIN from orders to order_items
CREATE INDEX IF NOT EXISTS idx_order_items_order_id
    ON order_items(order_id);

-- Speeds up inventory category search with stock filter
CREATE INDEX IF NOT EXISTS idx_inventory_category_stock
    ON inventory(category, stock)
    WHERE stock > 0;
