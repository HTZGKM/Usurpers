# Backend Testing Report

Last run: 2026-11-20

## Full-suite result

Command:

```powershell
python -m unittest discover -s tests -p 'test*.py' -v
```

Result: **32 tests run, 32 PASS, 0 FAIL**. The process-restart case requires localhost access; it passed when run with the required local-network permission. No test uses or resets the development database. Feature tests use `tests/.remaining_runtime/remaining.db`; existing suites use their own `.runtime` and `.edge_runtime` databases.

The test runner's default `python -m unittest discover -v` found zero tests because `tests` is not a package. Use the explicit `-s tests` command above.

## New tests in this pass

File: `tests/test_backend_remaining_features.py`

| Test | Status | Database evidence |
|---|---|---|
| `test_stock_reservation_prevents_oversell_and_cancel_releases` | PASS | `ingredients.reserved` stays within stock; only one reservation; cancellation changes reservation to released and returns reserved count to zero. |
| `test_concurrent_orders_cannot_reserve_the_same_last_stock` | PASS | Two actual threads race with a barrier; one order/reservation wins, the other receives a ServiceError; reserved stock is exactly the one available recipe quantity. |
| `test_starting_item_consumes_reserved_stock_once` | PASS | on-hand stock decreases, reserved returns to zero, reservation is consumed, one movement exists; repeated start conflicts. |
| `test_order_header_completes_only_after_all_lines_are_served` | PASS | The header remains active through partial work and becomes completed after every line is served. |
| `test_remake_is_separate_duplicate_safe_and_preserves_original` | PASS | Original line remains served; one linked remake ticket persists, duplicate active request conflicts, state advances independently. |
| `test_refund_is_idempotent_and_cumulative_amount_is_bounded` | PASS | Retry with same key returns same refund; over-refund rejected; only one refund row; original payment/order payment status retained. |
| `test_deactivated_customer_session_is_rejected_and_history_remains` | PASS | Existing cookie gets 403 and is cleared; order history remains; reactivation plus login restores access. |
| `test_background_tick_promotes_due_preorder_idempotently` | PASS | Worker tick promotes due line once; second tick inserts no duplicate kitchen queue row. |
| `test_flask_server_process_restart_recovers_persistent_queue` | PASS | Starts a real child Flask process, terminates it, starts a new process on the same test DB; cooking state and queue row count persist. This checks committed-state restart only, not kill during an open transaction. |

Existing suites remain in place: `test_service_api.py` (14 tests) and `test_backend_edge_cases.py` (9 tests). The previous “inventory/remake are blocked” assertion was replaced with an idempotent schema migration assertion because the modules now exist; functional behavior is tested by the new suite.

## Additional checks and gaps

- **Concurrency:** PASS for two simultaneous orders reserving the last configured stock. Not tested for concurrent booking last-table allocation, simultaneous table assignment, competing order edits, or multi-worker auto-call.
- **Process recovery:** PASS for a real Flask process terminate/restart with committed kitchen progress. In-flight transaction termination, power loss, and storage corruption: NOT TESTED.
- **Transactions:** Existing injected kitchen-queue and payment-write failure tests still pass. Inventory shortage and reservation writes use the same order transaction; direct SQL failure injection specifically between inventory reservation steps: NOT TESTED.
- **Inventory shortage:** PASS as full order rollback / 409 conflict when configured recipe stock is insufficient. Frontdesk alert and substitute/decline/refund workflow: BLOCKED pending product rules and implementation.
- **Paid item cancellation refund:** BLOCKED; refunds can be requested explicitly, but cancellation is not linked automatically to a refund.
- **Reservation interval/closure rules:** BLOCKED pending opening hours, booking duration, turnover buffer and cross-midnight rules.
- **Worker deployment:** task tick is tested; daemon command runs separately. Production process supervision and multi-worker lock behavior: NOT TESTED.
- **Role/data ownership coverage:** Earlier customer/role tests remain; every new route does not yet have dedicated role matrix and malformed-write API coverage: NOT TESTED.

No test failures are hidden as blocked; the status categories above distinguish actual tests from missing behavior.
