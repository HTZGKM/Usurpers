# Backend Implementation Status

Last reviewed: 2026-11-20

## Audit summary

The live Flask API is registered through `restaurant/api_routes.py`; the older role route modules are placeholder/template routes and are not separately registered in `app.py`. Services are in `restaurant/services/`. SQLite schema and additive migrations are in `restaurant/db/database.py`. The checked-in project Markdown is limited to the README files and backend edge-case plan/catalog; the role-route/auth requirement files supplied in the conversation were also used as requirements.

| Module | Current status | Evidence / limitation |
|---|---|---|
| Authentication, staff roles, staff deactivation | Implemented, partially tested | API role guard and active staff checks; customer deactivation added this round. |
| Booking | Partial | Discrete `time_slots`; booking/edit/cancel and availability work. No opening-hours calendar, interval overlap, turnover buffer, overnight hours, or closure calendar. |
| Table / arrival | Partial | Walk-in, check-in, assignment, close and occupancy; no table maintenance/CRUD or explicit cleaning state. |
| Orders / payments | Partial | Order-line price snapshots, transactional creation, line cancellation, payment idempotency; status summary added. No real gateway (by design), chargeback, or automated line-cancellation refund. |
| Menu | Partial | Dish availability/price/archive and admin create/edit; no recipe-aware availability notification flow to customers. |
| Ingredient inventory | Core implemented | Ingredient, recipe, movement and reservation records; stock is reserved in order transaction, released on waiting-line cancellation, consumed at start. Dishes without configured recipes are not stock controlled. |
| Remake / re-fire | Core implemented | Separate `remake_tickets`, source order line, reason, staff, state and timestamps. Active duplicate blocked. Kitchen queue response merges waiting remakes and ordinary lines; dedicated start/complete routes. |
| Refund | Core simulated implementation | Refund linked to payment, staff, reason and idempotency key; cumulative ceiling. No real payment provider, refund callback, item-level automatic refund, or order refund-summary status persisted. |
| Waiting queue | Partial | Durable queue, call/seat/cancel, timeout; prior table release calls next. Standalone worker now polls for expiry/promotion/available-table calls. No durable job scheduler/lease for multiple worker processes. |
| Kitchen queue | Partial | Durable queue and item state transitions; preorder promotion idempotent. Worker is opt-in and must be run separately. Remake history is separate from original production history. |
| Customer accounts | Partial | Admin activate/deactivate endpoints; deactivated login and old protected API sessions rejected; historical data retained. Existing reservations/orders are left unchanged while disabled. |
| Admin APIs | Partial | Staff/menu/orders/bookings/tables/session/queue/dashboard endpoints. Order and booking filters added. No full table CRUD, audit dashboard/reporting, or ingredient alert inbox. |
| Crash recovery | Partial | SQLite state survives a real Flask process terminate/restart test; process death during an uncommitted transaction and storage failure are not covered. |

## New database objects

- `ingredients`: unit, on-hand/reserved quantities, expiry and availability.
- `dish_ingredients`: per-dish recipe quantities.
- `inventory_reservations`: per-order-line ingredient reservation lifecycle.
- `inventory_movements`: stock audit trail.
- `remake_tickets`: independent remake history attached to the original order line.
- `refunds`: refund entries attached to the payment/order with unique idempotency key.
- `customers.is_active`: additive customer account state migration.

Schema creation and additive `ALTER TABLE` migrations run through idempotent `ensure_database()`. Existing development database was not reset in this work; all feature tests use `tests/.remaining_runtime/remaining.db` and the existing suites' isolated database paths.

## API additions / changes

- `GET /admin/inventory/ingredients`
- `POST /admin/inventory/ingredients`
- `POST /admin/inventory/ingredients/<ingredient_id>/adjust`
- `PUT /admin/dishes/<dish_id>/recipe`
- `POST /frontdesk/orders/<order_id>/items/<item_id>/remakes`
- `GET /kitchen/remakes?status=waiting|cooking|ready|completed|cancelled`
- `POST /kitchen/remakes/<remake_id>/start`
- `POST /kitchen/remakes/<remake_id>/complete`
- `POST /frontdesk/orders/<order_id>/refunds` (requires amount, reason, idempotency_key)
- `GET /frontdesk/orders/<order_id>/refunds`
- `GET /admin/accounts` includes staff and customer accounts.
- `POST /admin/customers/<customer_phone>/deactivate|activate`
- `GET /admin/orders` supports `status`, `active_only`, `phone_number`, `table_id` filters.
- `GET /admin/bookings` supports `booking_date`, `time_slot_id`, `phone_number` filters.

New write APIs return the existing ServiceError JSON contract. Refunds are simulated ledger entries and do not move money externally.

## Operational requirements and open decisions

- Start the background worker separately with `python -m restaurant.scheduler` (optional `--interval N`). The app does not start an embedded scheduler, avoiding duplicate jobs under Flask reloader.
- Assign recipes for every inventory-managed dish before relying on stock enforcement. Legacy/default dishes currently have no recipe and therefore no ingredient reservation.
- Confirm whether inventory shortage should reject the entire order (current behavior), permit partial order, notify a specific frontdesk inbox, and what substitution/refusal/refund workflow is expected.
- Confirm whether a disabled customer's future booking should be cancelled, held, or remain valid; current behavior retains all history and active business records.
- Define reservation duration, clean-table buffer, weekly/exception opening hours, cross-midnight policy, and behavior when hours change around existing bookings.
- Define expiry/scrap handling for already-reserved ingredients. The current start operation rejects unavailable/expired reserved ingredients, but automatic order notification and rebooking/refund are not implemented.
- Decide whether multiple scheduler workers must be supported; current safe retry behavior prevents duplicate preorder rows, but queue call distribution across multiple processes has not been validated.
- Define order-level partial refund state semantics and automatic refunds for cancelled paid items.

## Test status

The latest complete test run is 32 passing tests, 0 failing. It includes a true two-thread stock contention case and a separate-process Flask restart case. It does not mean every scenario in the edge-case plan is implemented or tested; see `backend_testing_report.md` and `backend_edge_case_test_plan.md`.
