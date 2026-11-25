BEGIN;
SET LOCAL lock_timeout = '5s';
SELECT pg_advisory_xact_lock(731593001);
CREATE EXTENSION IF NOT EXISTS btree_gist WITH SCHEMA public;

CREATE TABLE IF NOT EXISTS reservation_schema_versions (
    version integer PRIMARY KEY,
    applied_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    writes_enabled boolean NOT NULL DEFAULT true
);

ALTER TABLE dining_tables ADD COLUMN IF NOT EXISTS is_disabled boolean NOT NULL DEFAULT false;
ALTER TABLE bookings ADD COLUMN IF NOT EXISTS arrival_at timestamptz;
ALTER TABLE bookings ADD COLUMN IF NOT EXISTS arrival_deadline timestamptz;
ALTER TABLE bookings ADD COLUMN IF NOT EXISTS checked_in_at timestamptz;
ALTER TABLE bookings ADD COLUMN IF NOT EXISTS ready_at timestamptz;
ALTER TABLE bookings ADD COLUMN IF NOT EXISTS ready_table_id integer REFERENCES dining_tables;
ALTER TABLE bookings ADD COLUMN IF NOT EXISTS offered_table_id integer REFERENCES dining_tables;
ALTER TABLE bookings ADD COLUMN IF NOT EXISTS offer_expires_at timestamptz;
ALTER TABLE bookings ADD COLUMN IF NOT EXISTS table_consent_at timestamptz;
ALTER TABLE bookings ADD COLUMN IF NOT EXISTS no_show_at timestamptz;
ALTER TABLE bookings DROP CONSTRAINT IF EXISTS bookings_status_check;
ALTER TABLE bookings ADD CONSTRAINT bookings_status_check
    CHECK(status IN ('booked','arrived','cancelled','no_show'));

ALTER TABLE dining_sessions ADD COLUMN IF NOT EXISTS seated_at timestamptz;
ALTER TABLE dining_sessions ADD COLUMN IF NOT EXISTS clearance_processed_at timestamptz;
UPDATE dining_sessions SET clearance_processed_at=closed_at AT TIME ZONE 'UTC'
WHERE status='closed' AND seated_at IS NULL AND clearance_processed_at IS NULL
    AND NOT EXISTS(SELECT 1 FROM reservation_schema_versions WHERE version=2);
ALTER TABLE dining_sessions ADD COLUMN IF NOT EXISTS queue_id integer REFERENCES waiting_queue;
CREATE UNIQUE INDEX IF NOT EXISTS uq_dining_active_table
    ON dining_sessions(table_id) WHERE table_id IS NOT NULL AND status='seated';
CREATE UNIQUE INDEX IF NOT EXISTS uq_dining_queue_ticket ON dining_sessions(queue_id) WHERE queue_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_dining_booking ON dining_sessions(booking_id) WHERE booking_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_dining_closed_at ON dining_sessions(closed_at);

ALTER TABLE waiting_queue ADD COLUMN IF NOT EXISTS call_expires_at timestamptz;
ALTER TABLE waiting_queue ADD COLUMN IF NOT EXISTS ended_at timestamptz;
ALTER TABLE waiting_queue DROP CONSTRAINT IF EXISTS waiting_queue_status_check;
ALTER TABLE waiting_queue ADD CONSTRAINT waiting_queue_status_check
    CHECK(status IN ('waiting','called','seated','cancelled','expired','passed'));

CREATE TABLE IF NOT EXISTS table_holds (
    hold_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    table_id integer NOT NULL REFERENCES dining_tables,
    booking_id integer REFERENCES bookings,
    queue_id integer REFERENCES waiting_queue,
    kind text NOT NULL CHECK(kind IN ('reservation','offer','call')),
    protected_during tstzrange NOT NULL CHECK(NOT isempty(protected_during)),
    expires_at timestamptz,
    CHECK ((kind='call' AND queue_id IS NOT NULL AND booking_id IS NULL AND expires_at IS NOT NULL)
        OR (kind='reservation' AND booking_id IS NOT NULL AND queue_id IS NULL AND expires_at IS NULL)
        OR (kind='offer' AND booking_id IS NOT NULL AND queue_id IS NULL AND expires_at IS NOT NULL)),
    CONSTRAINT no_overlapping_table_holds
        EXCLUDE USING gist (table_id public.gist_int4_ops WITH =, protected_during WITH &&)
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_hold_per_booking_kind ON table_holds(booking_id,kind) WHERE booking_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_hold_per_call ON table_holds(queue_id) WHERE queue_id IS NOT NULL;

-- Keep legacy arrivals as windows. Historical dates and untrusted actual times stay as recorded.
UPDATE bookings SET arrival_deadline =
    (booking_date + split_part(time_slot,'-',2)::time) AT TIME ZONE 'Asia/Shanghai'
WHERE arrival_at IS NULL AND arrival_deadline IS NULL AND status='booked'
    AND booking_date >= (clock_timestamp() AT TIME ZONE 'Asia/Shanghai')::date;

INSERT INTO table_holds(table_id,booking_id,kind,protected_during)
SELECT table_id, booking_id, 'reservation', tstzrange(
    (booking_date + split_part(time_slot,'-',1)::time) AT TIME ZONE 'Asia/Shanghai', arrival_deadline, '[)')
FROM bookings b
WHERE arrival_at IS NULL AND arrival_deadline IS NOT NULL AND status='booked' AND table_id IS NOT NULL
    AND NOT EXISTS(SELECT 1 FROM table_holds h WHERE h.booking_id=b.booking_id AND h.kind='reservation');

UPDATE waiting_queue SET status='waiting', called_at=NULL, called_table_id=NULL
WHERE status='called' AND (called_at IS NULL OR called_table_id IS NULL);
UPDATE waiting_queue SET call_expires_at=(called_at AT TIME ZONE 'UTC') + interval '1 minute'
WHERE status='called' AND call_expires_at IS NULL;
INSERT INTO table_holds(table_id,queue_id,kind,protected_during,expires_at)
SELECT called_table_id, queue_id, 'call', tstzrange(called_at AT TIME ZONE 'UTC',
    call_expires_at + make_interval(mins => CASE WHEN GREATEST(party_size, COALESCE(table_type,0)) <= 2 THEN 55
        WHEN GREATEST(party_size, COALESCE(table_type,0)) <= 4 THEN 70 ELSE 85 END), '[)'), call_expires_at
FROM waiting_queue q WHERE status='called' AND call_expires_at >= clock_timestamp()
    AND NOT EXISTS(SELECT 1 FROM table_holds h WHERE h.queue_id=q.queue_id);

INSERT INTO reservation_schema_versions(version) VALUES(2) ON CONFLICT (version) DO NOTHING;
COMMIT;
