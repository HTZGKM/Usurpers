BEGIN;
SET LOCAL lock_timeout = '5s';

ALTER TABLE bookings ADD COLUMN IF NOT EXISTS version INTEGER NOT NULL DEFAULT 1 CHECK(version > 0);

CREATE TABLE IF NOT EXISTS booking_create_requests (
    customer_phone TEXT NOT NULL REFERENCES customers(customer_phone),
    request_key TEXT NOT NULL,
    request_fields TEXT NOT NULL,
    booking_id INTEGER NOT NULL REFERENCES bookings(booking_id),
    initial_table_id INTEGER NOT NULL REFERENCES dining_tables(table_id),
    PRIMARY KEY (customer_phone, request_key)
);

COMMIT;
