BEGIN;
SET LOCAL lock_timeout = '5s';
SELECT pg_advisory_xact_lock(731593001);

ALTER TABLE orders ADD COLUMN IF NOT EXISTS version INTEGER NOT NULL DEFAULT 1 CHECK(version > 0);
CREATE TABLE IF NOT EXISTS mutation_requests (
    scope TEXT NOT NULL, actor TEXT NOT NULL, request_key TEXT NOT NULL,
    fingerprint TEXT NOT NULL, result TEXT NOT NULL, PRIMARY KEY(scope,actor,request_key)
);

WITH missed AS (
    UPDATE orders o SET status='cancelled'
    FROM bookings b WHERE o.booking_id=b.booking_id AND b.status='no_show'
        AND o.visit_id IS NULL AND o.order_type='preorder' AND o.status='active' AND o.payment_status='unpaid'
        AND NOT EXISTS (SELECT 1 FROM order_items i WHERE i.order_id=o.order_id AND i.status IN ('cooking','ready','served'))
    RETURNING o.order_id
), cancelled_items AS (
    UPDATE order_items SET status='cancelled'
    WHERE status='waiting' AND order_id IN (SELECT order_id FROM missed)
)
UPDATE kitchen_queue SET status='cancelled',completed_at=clock_timestamp() AT TIME ZONE 'UTC'
WHERE status='waiting' AND order_id IN (SELECT order_id FROM missed);

INSERT INTO reservation_schema_versions(version) VALUES(3) ON CONFLICT (version) DO NOTHING;
COMMIT;
