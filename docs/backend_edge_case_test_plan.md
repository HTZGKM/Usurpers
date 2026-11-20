# Backend Edge Case Test Plan

## Scope and audit basis

Backend only. No HTML, CSS, JavaScript, or prototype behavior is part of this plan. Reviewed repository Markdown (root/prototype and template/static placeholders), the five user-supplied auth/customer/frontdesk/admin/kitchen route specifications, `app.py`, registered API routes, Services, SQLite schema/seeding/migrations, legacy role Route modules, Model placeholders, and the existing unittest suite.

The registered API is centralized in `restaurant/api_routes.py`. Older role route modules remain placeholders. Current suite has 31 tests across `test_service_api.py`, `test_backend_edge_cases.py`, and `test_backend_remaining_features.py`; no coverage tool is configured, so numeric code coverage is unknown. Latest full run: 31 PASS, 0 FAIL.

### Status meanings

- **PASS / FAIL**: executed test result.
- **BLOCKED**: required business feature or infrastructure does not exist; test cannot meaningfully pass yet.
- **NOT TESTED**: behavior exists or can be exercised, but this test has not been run.

`Current Support` describes code evidence before the edge-test run, not a claim of correctness.

## Existing coverage and feature gaps

| Area | Existing coverage | Current support / notable gaps |
|---|---|---|
| Registration/authentication | Basic auth paths, role guard, customer disable/re-enable | Customer active flag and existing-session rejection now exist; password hashing remains legacy SHA-256; cookie/session expiry and CSRF policy are not tested. |
| Reservation/table/check-in | Invalid booking no-write, basic table capacity exhaustion, called-party after release | Exact time-slot reservation and `BEGIN IMMEDIATE` exist; no concurrent-process stress test; late/no-show policy absent. |
| Guest handling | Walk-in invalid input | Guest identity fields and staff-created reservations/orders exist; duplicate guest scenarios need more testing. |
| Orders | Invalid item list and isolated kitchen line | Menu availability and saved unit price exist; no client idempotency key; no tested write-fault rollback. |
| Menu/supply | Stock reservation, concurrent contention, release and consumption | Recipe inventory exists; legacy dishes without recipes are not stock controlled; substitution/notification flow absent. |
| Kitchen | Independent line state, remake state, preorder promotion, process restart | Persistent queue and separate remake ticket exist; delivery incident metadata beyond reason/actor is not modeled. |
| Waiting queue | Duplicate, cancel, timeout, release/call-next, scheduled tick | Standalone scheduler worker exists; queue auto-call under multiple workers is untested. |
| Payment/refund | Duplicate payment and simulated refund idempotency/cap | Refund ledger exists; no real gateway or automatic paid-line refund link. |
| Persistence/recovery | Seed idempotency and true process restart | Committed state restart tested; process kill during an open transaction/disk failure not tested. |
| Models | None | `restaurant/models/*.py` are placeholders; Services query SQLite rows directly. |

## Scenario matrix

| Test ID | Module | Scenario | Preconditions | Steps | Expected Result | Database Validation | Priority | Current Support | Test Status |
|---|---|---|---|---|---|---|---|---|---|
| RES-001 | Reservation | Customer creates a valid booking | Customer session; open slot and fitting table | POST `/bookings` | 201 | One booking, customer ownership and table assignment saved | P0 | Implemented | PASS |
| RES-002 | Reservation | Customer changes slot/table/party size | Owned booking in `booked` state | POST edit with a feasible new slot and party size | Success | New values committed; old values replaced | P0 | Implemented | NOT TESTED |
| RES-003 | Reservation | New slot has no fitting table | Slot fully reserved | Modify booking | 409 | Original booking remains unchanged | P0 | Implemented | PASS |
| RES-004 | Reservation | Customer cancels then repeats cancellation | Owned active booking | Cancel twice | First success; second conflict | Status cancelled once; released capacity available | P1 | Implemented | NOT TESTED |
| RES-005 | Reservation | Two requests compete for the last fitting table | One suitable table remains | Concurrently create two bookings | Exactly one succeeds | One active allocation; no duplicate table/slot assignment | P0 | Transaction implemented; race untested | NOT TESTED |
| RES-006 | Reservation | Customer is late / does not arrive / booking is in past | Booking is active | Attempt check-in or query after slot | Policy-specific response | No accidental session or table leak | P1 | Late/no-show policy absent | BLOCKED |
| RES-007 | Reservation | Customer A edits/cancels Customer B booking | Two customer accounts and bookings | Request B's booking as A | 404/403 | B's row unchanged | P0 | Ownership checks exist | PASS |
| GUEST-001 | Guest | Frontdesk books guest without website account | New phone number | POST `/frontdesk/bookings` | 201 | Guest name/phone saved without customer FK | P1 | Implemented | NOT TESTED |
| GUEST-002 | Guest | Missing guest name/phone or malformed phone | Frontdesk session | Submit incomplete values | 400 JSON | No booking/session/order added | P0 | Validators exist | NOT TESTED |
| GUEST-003 | Guest | Guest walk-in and order through visit | Open fitting table | Register walk-in, create order, pay and close | Success end-to-end | Session/order/table links agree | P1 | Partially implemented | NOT TESTED |
| GUEST-004 | Guest/Auth | Customer account disabled but session retained | Customer active session | Disable account then request API | Denied | No new business write | P0 | Implemented and tested as CUST-001 | PASS |
| ORD-001 | Order | Same client retries order after response timeout | Active visit | Submit identical order twice | Idempotent response expected | One logical order/line set | P0 | No idempotency key | BLOCKED |
| ORD-002 | Order | Quantity zero/negative, unknown dish, sold-out dish | Active visit | Submit invalid lines | 400/404/409 JSON | No order header, lines, or queue rows | P0 | Validation exists | NOT TESTED |
| ORD-003 | Order | DB failure halfway through header/line/queue inserts | Fault injection trigger | Submit a multi-item order | 500 JSON | Entire operation rolls back; no orphan rows | P0 | Transaction exists | PASS |
| ORD-004 | Order | Two staff edit same order concurrently | Unpaid, all lines waiting | Concurrent edits | One wins or deterministic conflict | No mixed/duplicate line and queue state | P0 | Transaction exists; optimistic version absent | NOT TESTED |
| ORD-005 | Order | Edit after payment or after preparation starts | Paid / cooking order | Attempt edit | 409 | Header/lines/queue remain unchanged | P0 | Business checks exist | NOT TESTED |
| ORD-006 | Order | Cancel one of multiple dishes | Unpaid order with multiple waiting lines | Cancel one line | Success | Only selected line and queue row cancelled; total recalculated | P0 | Implemented | NOT TESTED |
| MENU-001 | Menu | Menu price changes after order | Existing line with unit price snapshot | Update dish price | Success | Historical order total unchanged | P0 | Snapshot exists | NOT TESTED |
| MENU-002 | Menu | Duplicate dish name during edit | Another dish owns name | Edit name | 409 JSON | No partial update | P1 | Service precheck in transaction | PASS |
| INV-001 | Ingredient inventory | Reserve/deduct/release ingredients across orders | Ingredient and recipe configured | Reserve, cancel, start production | Insufficient stock is rejected; waiting cancellation releases; start consumes | Reservation, on-hand, movement rows agree | P0 | Implemented for configured recipes | PASS |
| INV-002 | Ingredient inventory | Spoiled/expired stock; shortage and substitutions | Inventory and substitution policy | Mark stock unusable; handle existing orders | Frontdesk notified; customer accepts/declines replacement | No oversell; release/refund path recorded | P0 | Stock shortage/expiry blocks write/start; notification and substitution policy absent | BLOCKED |
| KITCH-001 | Kitchen | Item enters queue once and transitions waiting→cooking→ready→served | Valid order line | Repeat enqueue/start/finish/serve calls | Legal transition succeeds; illegal repeat conflicts | One queue row; only target line changes | P0 | Implemented | NOT TESTED |
| KITCH-002 | Kitchen | Cancelled item remains in queue | Multi-line unpaid order | Cancel one item; read queue | Cancelled item absent from active queue | Other items retain status | P0 | Implemented | NOT TESTED |
| KITCH-003 | Kitchen | Wrong-table delivery and remake/refire | Served item marked misdelivered | Record incident and create remake | New linked remake task | Original item/history unchanged; remake has actor/reason/time/state | P1 | Separate remake ticket and queue routes | PASS |
| KITCH-004 | Kitchen | Two kitchen employees update same item | One waiting item | Concurrent start/complete | One valid transition; other conflict | No double completion/task | P0 | Conditional update exists; concurrent test absent | NOT TESTED |
| KITCH-005 | Kitchen/Recovery | Process restarts with cooking item | Persistent cooking queue row | Restart Flask process and inspect DB | Item restored as cooking, not duplicated | Same queue id and state | P0 | Real process test | PASS |
| PAY-001 | Payment | Normal pay and repeated request after lost response | Unpaid active order | Pay twice | First paid; retry returns same paid result | Exactly one payment row; amount equals live payable lines at commit | P0 | Idempotent unique row exists | PASS |
| PAY-002 | Payment/Auth | Kitchen/customer attempts unauthorized payment alias | Signed-in non-paying role | POST `/pay/<id>` | 403 | No payment/order change | P0 | Payment alias guard added | PASS |
| PAY-003 | Payment | Cancelled order or amount tampering | Cancelled order / client sends amount | Attempt payment | 409 or amount ignored | No client amount trusted; no payment row for cancelled order | P0 | Amount derived; alias and cancellation checks need tests | NOT TESTED |
| PAY-004 | Payment | DB fails between payment row and order status update | Injected DB failure | Submit pay | 500 JSON | Both payment row and paid state roll back | P0 | Same transaction | PASS |
| PAY-005 | Refund | Partial refund after one dish cancelled | Paid order and staff actor | Submit refund with idempotency key | Auditable simulated refund | Refund sum <= captured amount; original payment retained | P1 | Explicit refund ledger; automatic paid-line cancellation linkage absent | NOT TESTED |
| WQ-001 | Waiting queue | Duplicate join/cancel/timeout | Customer or guest entry | Join twice, cancel or age called entry | Duplicate rejected; cancel/expire terminal | Single active entry; no seat assignment after expiry | P1 | Implemented; lazy expiry | PASS |
| WQ-002 | Waiting queue | Table release and repeated seat attempt | Freeable table, ordered queue | Release/call next; retry same seat request | At most one party seated | One active visit/table; queue status consistent | P0 | Release calls next; sequential test | PASS |
| WQ-003 | Waiting queue | Recreate app with persistent queue | Persistent queue entries | Recreate Flask app | Queue loads; status persists | No duplicate entry/seat | P1 | Same-process app recreation tested | PASS |
| KQ-001 | Kitchen queue | Preorder enters only at expected time and sorts by priority/time | Future and due preorders | Query before/after due time | Future excluded; due item ordered correctly | One queue row per order item; no early enqueue | P0 | Promotion exists; priority ordering not tested | NOT TESTED |
| KQ-002 | Kitchen queue | Cancelled line and remake queue behavior | Cancelled/original line | Refresh queue; add remake if supported | Cancelled excluded; remake separate | History preserved | P1 | Cancellation exists; remake BLOCKED | NOT TESTED |
| AUTH-001 | Role permissions | Customer, frontdesk, kitchen, admin call cross-role APIs | Four sessions | Exercise protected paths incl. aliases | 401/403 by role matrix | No unauthorized writes | P0 | Partial path-prefix guard | NOT TESTED |
| AUTH-002 | Data ownership | Customer A reads/updates B's bookings/orders/waitlist | Two customers | Access each other's ids | 404/403 | Target rows unchanged | P0 | Some owner filters exist | NOT TESTED |
| EMP-001 | Employee | Deactivated staff reuses existing cookie | Staff session then admin disables | Call staff API | 403 and session cleared | No write | P0 | API guard exists | NOT TESTED |
| CUST-001 | Customer account | Deactivate customer with existing session and historical orders | Customer + admin sessions | Deactivate, reuse cookie, reactivate and sign in | Old cookie rejected; history retained; re-enabled login works | Account flag changes; order history unchanged | P0 | Implemented and tested | PASS |
| DB-001 | Transactions | DB connection drops during each multi-write workflow | SQLite fault injection | Fail after first write | Generic JSON 500 | All related writes rolled back | P0 | Transactions used selectively; incomplete coverage | NOT TESTED |
| DB-002 | Migration | Run initialization repeatedly on existing data | Existing dev DB and isolated test DB | Run migration twice | No loss/duplicate rows | Foreign keys valid; stable counts | P0 | Seed/migration idempotence tested | PASS |
| REC-001 | Recovery | Recreate app after committed kitchen progress | Durable DB state | Recreate Flask app | Committed state reloaded without duplicate task | Queue row and state persist | P0 | Same-process recreation tested | PASS |
| REC-002 | Crash simulation | Restart a real Flask process with committed active kitchen work | Isolated durable test DB | Terminate server process, start a new process | Committed queue state recovers without duplicate | Same queue row and cooking status remain | P0 | Real process restart test; in-flight transaction kill and disk failure not tested | PASS |
| SCHED-001 | Background scheduler | Due preorder promoted without an API read | Due preorder and separate worker tick | Execute scheduled task twice | First tick promotes; retry has no duplicate | One kitchen queue row | P0 | Standalone worker implemented; tick test passes | PASS |

## Planned automation

Current automated suites: `tests/test_service_api.py`, `tests/test_backend_edge_cases.py`, and `tests/test_backend_remaining_features.py`. Remaining tests include:

- `test_booking_edge_cases.py`: reservation ownership, failed edit preservation, repeat cancel, late/no-show policy once defined, last-table contention.
- `test_customer_edge_cases.py`: account registration, guest flows, customer disable policy, cross-customer reads and writes.
- `test_order_edge_cases.py`: invalid lines, duplicate request semantics, cancellation isolation, update/payment races, rollback injection.
- Inventory: spoilage of already reserved stock, alert/substitution/refusal flow, direct fault injection during reservations.
- Kitchen: concurrent worker state transitions, remake cancellation and separate lifecycle recovery.
- Payment: wrong-amount invalid input, duplicate idempotency key with mismatched request, automatic refund of cancelled paid item.
- `test_queue_edge_cases.py`: timeout, auto-call, duplicate seat contention, priority and durable restart behavior.
- `test_recovery_edge_cases.py`: app restart and SQLite transaction fault injection; process-kill scope reported separately from physical disk/power failure.

Tests must use `USURPERS_DB_PATH` pointing at an isolated database. Do not run `--reset` against `restaurant/data/shuangfen.db`.

## Discovered issues and current disposition

1. **Fixed:** `POST /pay/<order_id>` lacked an explicit role rule; kitchen users could pay. A route-level role rule and no-write test now cover it.
2. **Fixed:** Dish rename collisions returned generic 500. The Service now checks uniqueness inside a write transaction and returns 409 without partial change.
3. **Partly fixed:** Test modules now resolve separate SQLite paths at call time and edge tests reset their own test DB per case. The older service suite still uses a shared client/database within that suite, so test-order sensitivity remains a risk.
4. **Implemented:** Standalone scheduler tick handles timeout, due preorder promotion and free-table call-next; it must be run as a worker process.
5. **Open:** Substitutions, frontdesk shortage notifications, paid-line automatic refund, full reservation business hours, and multi-worker scheduling remain feature gaps.

## Edge-test execution report

Superseded execution details are maintained in `docs/backend_testing_report.md`. Latest full run used `python -m unittest discover -s tests -p 'test*.py' -v` on isolated SQLite paths: **31 tests passed, 0 failed**.

New edge tests in `tests/test_backend_edge_cases.py`:

| Test | Result | Database evidence |
|---|---|---|
| Kitchen role rejected by customer payment alias | PASS after fix | Order remained unpaid; payment count stayed zero |
| Duplicate dish name edit | PASS after fix | HTTP 409 JSON; original name and price unchanged |
| Failed reservation edit preserves original | PASS | Original date, slot, party size, table, and status unchanged |
| Cross-customer booking cancellation | PASS | Other customer's booking remained booked |
| Kitchen-queue insert fault during order creation | PASS | Header, line, and queue counts rolled back |
| Payment status update fault | PASS | Payment row absent and order remained unpaid |
| Repeated seating of one called queue item | PASS | Exactly one active visit created |
| Flask app recreation with cooking item | PASS (limited recovery scope) | Queue row count and cooking state persisted |
| Inventory/remake schema migration | PASS | Tables created idempotently and functional behavior is covered in the remaining-feature suite |

Initial edge-test execution found two real defects: the `/pay/<id>` alias allowed a kitchen session to pay, and duplicate dish names produced HTTP 500. Role guarding and transactional duplicate-name validation were fixed; both tests now pass. The reservation-edit test initially used an available original table, so that test setup was corrected to fully occupy the target slot. A full-suite run then exposed a shared test database path: a fault-injection trigger leaked across test modules. Database path resolution now occurs at connection/migration time, and each test suite selects its own database; the final full run passes.

The separate-process test verifies committed-state restart only; it is not an in-flight transaction, power-loss, disk-failure, or database-corruption test. One true concurrent two-thread stock reservation test passes. Concurrent bookings, table assignments, order edits, and multi-worker scheduler execution remain NOT TESTED. Inventory shortage substitution/notification and paid-item automatic refund remain BLOCKED pending business rules and implementation.
