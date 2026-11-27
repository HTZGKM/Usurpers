BEGIN;
SET LOCAL lock_timeout='5s';
SELECT pg_advisory_xact_lock(731593001);
ALTER TABLE order_items ADD COLUMN IF NOT EXISTS dish_name_snapshot TEXT;
ALTER TABLE order_items ADD COLUMN IF NOT EXISTS category_snapshot TEXT;
ALTER TABLE order_items ADD COLUMN IF NOT EXISTS supply_issue TEXT;
ALTER TABLE order_items ADD COLUMN IF NOT EXISTS issue_reported_by TEXT;
ALTER TABLE order_items ADD COLUMN IF NOT EXISTS issue_reported_at TIMESTAMP;
-- Legacy snapshots use the best currently available menu metadata; past renames cannot be reconstructed.
UPDATE order_items i SET dish_name_snapshot=d.dish_name,category_snapshot=d.category FROM dishes d
WHERE d.dish_id=i.dish_id AND i.dish_name_snapshot IS NULL;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS replaces_item_id INTEGER REFERENCES order_items(order_item_id);
ALTER TABLE orders ADD COLUMN IF NOT EXISTS served_by TEXT;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS served_at TIMESTAMP;
CREATE TABLE IF NOT EXISTS kitchen_settings(id INTEGER PRIMARY KEY CHECK(id=1),max_active_orders INTEGER NOT NULL CHECK(max_active_orders BETWEEN 1 AND 100),version INTEGER NOT NULL DEFAULT 1);
INSERT INTO kitchen_settings(id,max_active_orders) VALUES(1,5) ON CONFLICT(id) DO NOTHING;
CREATE TABLE IF NOT EXISTS kitchen_settings_audit(id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,actor TEXT NOT NULL,old_limit INTEGER NOT NULL,new_limit INTEGER NOT NULL,changed_at TIMESTAMP NOT NULL DEFAULT (CURRENT_TIMESTAMP AT TIME ZONE 'UTC'));
CREATE TABLE IF NOT EXISTS order_resolution_audit(id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,order_item_id INTEGER NOT NULL REFERENCES order_items,action TEXT NOT NULL CHECK(action IN ('cancel','replace')),reason TEXT NOT NULL,actor TEXT NOT NULL,replacement_order_id INTEGER REFERENCES orders,created_at TIMESTAMP NOT NULL DEFAULT (CURRENT_TIMESTAMP AT TIME ZONE 'UTC'));
INSERT INTO reservation_schema_versions(version) VALUES(7) ON CONFLICT(version) DO NOTHING;
COMMIT;
