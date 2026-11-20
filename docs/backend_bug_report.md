# Backend Bug Report

Last reviewed: 2026-11-20

## Fixed in this pass

| ID | Bug / gap | Impact | Fix | Verification |
|---|---|---|---|---|
| INV-01 | Orders had no ingredient reservation or shortage guard | Concurrent orders could consume the same assumed final stock | Added recipes, transactional reservation, shortage rejection, cancellation release, start-time consumption and movement records | `test_stock_reservation_prevents_oversell_and_cancel_releases`, `test_concurrent_orders_cannot_reserve_the_same_last_stock`, `test_starting_item_consumes_reserved_stock_once` |
| KITCH-01 | No independent refire record for a served item delivered to the wrong table | Reproduction would overwrite or be indistinguishable from original production | Added separate remake ticket linked to original item, reason, staff and timestamps; duplicate active ticket rejected | `test_remake_is_separate_duplicate_safe_and_preserves_original` |
| PAY-REF-01 | No refund ledger/idempotency/cumulative cap | A refund could be duplicated or exceed payment if implemented ad hoc | Added simulated refund records and transactionally enforced key, payment link, positive amount and cumulative ceiling | `test_refund_is_idempotent_and_cumulative_amount_is_bounded` |
| AUTH-CUST-01 | Customer accounts had no active flag and old sessions were not invalidated | Disabled accounts could keep using existing session cookies | Added additive `is_active`, login and request checks; old session cleared; admin activate/deactivate APIs | `test_deactivated_customer_session_is_rejected_and_history_remains` |
| SCHED-01 | Queue timeout and preorder promotion relied on API access | Tasks could remain pending when no one queried the relevant endpoint | Added standalone periodic worker and idempotent task tick | `test_background_tick_promotes_due_preorder_idempotently` |
| ORD-STATUS-01 | Order header could remain `active` after all lines were served or cancelled | Header summary could conflict with line states | Recalculate to `completed`, `cancelled`, or `active` after item serving/cancellation | Covered indirectly by existing transition tests; dedicated aggregate-state combinations remain NOT TESTED. |

## Known issues / incomplete behavior

1. A dish with no `dish_ingredients` recipe currently has no inventory enforcement. Existing/default dishes have not been assigned recipes because ingredient quantities were not supplied.
2. Inventory shortage returns a conflict and rolls back the complete order. There is no persisted frontdesk alert, substitution proposal/acceptance, or customer decline/refund flow.
3. Marking stock unavailable/expired prevents it being consumed at kitchen start, but there is no automatic resolution workflow for lines already holding that reservation.
4. Refund API is a local simulated ledger; no external payment gateway is integrated. Cancelling an already-paid item does not automatically issue a refund; a staff refund request is separate.
5. Remake route currently permits frontdesk/admin actors. Kitchen users can list and transition remakes, but authorization scope should be confirmed against the role policy document.
6. The scheduler is a separate worker process. There is no leader lease; deploy one worker instance. Idempotent DB operations prevent duplicate preorder queue rows, but concurrent multi-worker queue calls have not been stress-tested.
7. Reservation availability only compares the same discrete `time_slot_id`. Duration, real intervals, turnover, overnight opening and closure exceptions are not modeled.
8. Database transactions roll back injected SQL errors, and committed state survived process termination/restart. Abrupt kill in the middle of a transaction and disk/database corruption recovery remain NOT TESTED.
9. The app still uses a development `SECRET_KEY` literal. Production deployment must provide a secret via configuration; this was pre-existing and not changed as part of the requested business features.

## Reproduction / evidence

Run the isolated suite with:

```powershell
python -m unittest discover -s tests -p 'test*.py' -v
```

The process-restart test needs permission to bind localhost on restricted environments. It uses the test DB path only and never resets the development database.
