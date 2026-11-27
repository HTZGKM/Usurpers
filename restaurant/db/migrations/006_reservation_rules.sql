BEGIN;
SET LOCAL lock_timeout = '5s';
SELECT pg_advisory_xact_lock(731593001);

ALTER TABLE bookings ADD COLUMN IF NOT EXISTS transferred_queue_id integer REFERENCES waiting_queue;
ALTER TABLE bookings ADD COLUMN IF NOT EXISTS transferred_at timestamptz;
ALTER TABLE bookings DROP CONSTRAINT IF EXISTS bookings_status_check;
ALTER TABLE bookings ADD CONSTRAINT bookings_status_check CHECK(status IN ('booked','arrived','cancelled','no_show','transferred'));
ALTER TABLE waiting_queue ADD COLUMN IF NOT EXISTS source_booking_id integer REFERENCES bookings;
ALTER TABLE waiting_queue ADD COLUMN IF NOT EXISTS service_ends_at timestamptz;
ALTER TABLE waiting_queue ADD COLUMN IF NOT EXISTS version integer NOT NULL DEFAULT 1 CHECK(version > 0);
ALTER TABLE waiting_queue DROP CONSTRAINT IF EXISTS waiting_queue_status_check;
ALTER TABLE waiting_queue ADD CONSTRAINT waiting_queue_status_check CHECK(status IN ('waiting','called','seated','cancelled','expired','passed','service_ended'));
UPDATE waiting_queue SET service_ends_at = (
    (created_at AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Shanghai')::date +
    CASE WHEN (created_at AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Shanghai')::time < time '14:00'
         THEN time '14:00' ELSE time '21:00' END
) AT TIME ZONE 'Asia/Shanghai' WHERE service_ends_at IS NULL;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS queue_id integer REFERENCES waiting_queue;
ALTER TABLE dining_sessions ADD COLUMN IF NOT EXISTS cleared_by_actor text;
CREATE TABLE IF NOT EXISTS booking_table_changes (
    change_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    booking_id integer NOT NULL REFERENCES bookings,
    from_table_id integer REFERENCES dining_tables,
    to_table_id integer REFERENCES dining_tables,
    actor text NOT NULL,
    changed_at timestamptz NOT NULL,
    reason text NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_booking_table_changes ON booking_table_changes(booking_id,changed_at);
CREATE INDEX IF NOT EXISTS idx_waiting_service_end ON waiting_queue(service_ends_at) WHERE status IN ('waiting','called');
CREATE INDEX IF NOT EXISTS idx_orders_queue ON orders(queue_id) WHERE queue_id IS NOT NULL;
INSERT INTO reservation_schema_versions(version) VALUES(6) ON CONFLICT(version) DO NOTHING;
COMMIT;
